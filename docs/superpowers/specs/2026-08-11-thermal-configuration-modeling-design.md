# Modelado por configuraciones: reducir datos por-unidad de Paratec a TMG/ramps — diseño

Fecha: 2026-08-11
Issue: #26
Roadmap: `docs/roadmap-aplicacion-despacho.md`, memoria `project_thermal-configuration-dispatch`

## Contexto

El despacho real de XM es por **configuración**, no por planta plana. Una planta
térmica registra múltiples configuraciones (ej. "1 TV" vs "2 TV") con distinto
`maximumAvailability`/`technicalMinimum`, construidas a partir de unidades
individuales. Paratec expone:

- **Por unidad** (`ThermalUnit/ThermalFuelUnitInfo`): `minGenerationTime` (TMG real),
  `uploadSpeed`, `downloadSpeed`.
- **Por configuración** (`ThermalPlant.getThermalPlantDetail.configurations`):
  `maximumAvailability`, `technicalMinimum`, `ramps` (anidado por `configurationNumber`).

El modelo actual (`app/model/model.py` + `app/pipeline/case_builder.py`) trata cada
generador térmico como un recurso plano con escalares únicos:
- `TMG` desde `parametros_plantas.csv` (hoy hardcodeado a `1` en el fixture).
- `ramp_up == ramp_down` desde `ramps.json` (hoy `{}` vacío → default 10000 MW/h,
  sin restricción de rampa activa).
- `Pmin` hardcodeado a `{}` → default `max_min_op` (0 para ideal, 1 para preideal).

Este documento responde las tres preguntas del issue #26 y propone un camino de
implementación en fases que no rompe el modelo actual.

## 1. ¿Recursos planos o unidades/configuraciones?

### Recomendación: modelar configuraciones como recursos, sin cambiar la topología del modelo

**Opción seleccionada: cada configuración de planta es un recurso independiente en el
set `G` del modelo, con una restricción de exclusividad por planta.**

Esto replica el patrón ya existente para ciclo combinado (CC): cada configuración CC
(`FLORES 4 CC_1`, `FLORES 4 CC_2`) es un recurso separado, y `exclude_resource_rule`
evita que se despachen simultáneamente. Para plantas térmicas convencionales, la
restricción de exclusividad es análoga pero más simple: **a lo sumo una configuración
por planta encendida en cada t**:

```
sum_{c in configs(p)} z[c, t] <= 1   para toda planta p, todo t
```

Donde `z[c, t]` es la variable binaria de encendido/apagado (ya existe en el modelo).

### Opciones descartadas

| Opción | Por qué no |
|---|---|
| **Unidades individuales** (cada TV/ TG como recurso) | Requiere modelar relación unidad→planta (combustible común, punto de conexión), acoplamiento entre unidades de una misma planta, y restricciones de combinación válida (no todas las combinaciones de unidades son configuraciones reales). Complejidad desproporcionada para la precisión ganada. |
| **Quedarse con recursos planos** indefinidamente | Ignora datos reales de Paratec ya disponibles. El TMG hardcodeado a 1 y rampas vacías son placeholders que degradan la calidad del despacho — desde Fase 2B se documentó que el modelo no valida contra datos reales, y esta es una de las causas. |

### Precedente en el código

El modelo ya maneja el concepto de "múltiples recursos mutuamente excluyentes para una
misma planta física" en ciclo combinado (líneas 221–296 de `case_builder.py`, método
`_create_constraints` → `exclude_resource_rule`). La extensión a configuraciones de
plantas térmicas convencionales usa el mismo patrón: la planta física se representa
como un conjunto de recursos-configuración, y una restricción de exclusividad garantiza
que no se despachen dos configuraciones de la misma planta a la vez.

## 2. ¿Cómo se selecciona la "mejor configuración"?

**No se selecciona a priori: la elige el solver como resultado de la optimización.**

El modelo recibe **todas** las configuraciones viables de cada planta como recursos
separados en el set `G`, cada una con sus propios parámetros (`Pmax`, `Pmin`, `TMG`,
`RU`, `RD`, `beta`). La restricción de exclusividad (sección 1) obliga al solver a
escoger a lo sumo una por planta en cada instante. El costo total (función objetivo)
incorpora el `beta` de cada configuración, que puede diferir (una configuración con más
unidades puede tener un costo marginal distinto).

En el preideal (donde el modelo fija el commitment del predespacho ideal en vez de
optimizarlo), la "mejor configuración" viene del predespacho mismo — se lee qué
configuración estaba despachada en el predespacho ideal de XM y se usa esa. Esto es
análogo a cómo el `preideal_dispatch_map.json` ya fija el commitment para el nivel
`preideal`.

### Resumen del flujo por nivel de despacho

| Nivel | Cómo se selecciona la configuración |
|---|---|
| `preideal` | Leída del archivo de predespacho ideal (PrId*.txt), análogo al `preideal_dispatch_map.json` actual |
| `ideal` | El solver MILP escoge la configuración que minimiza el costo total, sujeto a la restricción de exclusividad |

## 3. Regla de reducción: datos por-unidad → escalares por-configuración

### Fuente de datos

Los datos por-unidad y por-configuración vienen de dos endpoints de Paratec:

| Endpoint | Qué expone | Uso |
|---|---|---|
| `ThermalUnit.getAll` / `ThermalFuelUnitInfo` | `minGenerationTime`, `uploadSpeed`, `downloadSpeed` por unidad | Reducción a escalares por configuración cuando `ThermalPlant.getThermalPlantDetail` no está disponible |
| `ThermalPlant.getThermalPlantDetail` | `configurations[]` con `maximumAvailability`, `technicalMinimum`, `ramps` por `configurationNumber` | Fuente primaria (la configuración ya está precomputada por XM) |

La capa de ingesta (`docs/superpowers/specs/2026-08-06-ingesta-storage-xm-design.md`)
cachea el JSON crudo de ambos endpoints sin interpretarlo. La interpretación ocurre en
una nueva función de `case_builder.py` (o módulo dedicado `app/data/paratec.py`).

### TMG — Tiempo Mínimo de Generación

`minGenerationTime` es inherentemente por-unidad: es el tiempo mínimo que una unidad
individual debe permanecer encendida una vez arranca. Para una configuración de N
unidades:

```
TMG_config = max(minGenerationTime_i for i in units_in_config)
```

**Justificación**: si una unidad requiere 4 horas mínimas online y otra 2 horas, la
configuración completa debe mantenerse al menos 4 horas — no se puede apagar la unidad
más restrictiva y mantener la configuración "parcialmente". El modelo actual no tiene
variable binaria por unidad dentro de una configuración, así que el TMG se aplica a la
configuración como un todo.

> **Nota**: `minGenerationTime` de Paratec es un dato real, no el placeholder `1` del
> `parametros_plantas.csv` actual. Este es uno de los beneficios inmediatos de esta
> migración.

### Rampas — RU / RD

**Preferir `ramps` por configuración de `ThermalPlant.getThermalPlantDetail`** (fuente
primaria). Si no está disponible, reducir desde `uploadSpeed`/`downloadSpeed` por unidad:

```
RU_config = sum(uploadSpeed_i for i in units_in_config)       # MW/h
RD_config = sum(downloadSpeed_i for i in units_in_config)     # MW/h
```

**Justificación**: las rampas de todas las unidades en una configuración son aditivas
(todas las unidades están operando simultáneamente y pueden rampear en paralelo).

**Caso actual**: `ramp_up == ramp_down` (mismo valor para ambas direcciones desde
`ramps.json`). Con datos de Paratec, `uploadSpeed` y `downloadSpeed` pueden diferir, y
el modelo ya soporta `RU != RD` (son dos `Param` independientes en `model.py:106-118`).
No se requiere cambio de modelo para explotar esta diferencia — solo dejar de asignar
el mismo diccionario a ambos parámetros en `case_builder.py:517-518`.

### Pmax y Pmin por configuración

`maximumAvailability` y `technicalMinimum` por configuración vienen de
`ThermalPlant.getThermalPlantDetail` y reemplazan los valores planos actuales de
`dispo_declarada.csv` y `Pmin = {}`.

```
Pmax[config, t] = maximumAvailability_config               # MW (escalado a unidades del modelo)
Pmin[config, t] = technicalMinimum_config                  # MW (escalado a unidades del modelo)
```

> **Cuidado con unidades**: `dispo_declarada.csv` está en **kW**, escalado x1e-3 → MW
> en `case_builder.py:386-391`. `maximumAvailability` de Paratec debe verificarse contra
> valores conocidos antes de asumir una unidad. Ver gotcha de unidades en
> `.agents/rules/overview.mdc`.

### Tabla resumen de reglas de reducción

| Parámetro del modelo | Fuente primaria (Paratec) | Fuente secundaria (reducción) | Unidad |
|---|---|---|---|
| `TMG[g]` | — (no hay TMG por configuración en Paratec) | `max(minGenerationTime_i)` de las unidades de la configuración | horas (entero) |
| `RU[g]` | `ramps[configurationNumber].upload` del endpoint `ThermalPlant.getThermalPlantDetail` | `sum(uploadSpeed_i)` de las unidades de la configuración | MW/h |
| `RD[g]` | `ramps[configurationNumber].download` del endpoint `ThermalPlant.getThermalPlantDetail` | `sum(downloadSpeed_i)` de las unidades de la configuración | MW/h |
| `Pmax[g, t]` | `maximumAvailability` de la configuración | `sum(Pmax_unit_i)` | MW |
| `Pmin[g, t]` | `technicalMinimum` de la configuración | `max(Pmin_unit_i)` | MW |
| `beta[g]` | Precio de oferta por configuración desde Paratec (si disponible) o desde `ofertas.csv` | — | COP/MWh |

## 4. Camino de implementación (fases)

### Fase A — Normalización de datos (sin cambio de modelo)

**Objetivo**: reemplazar los placeholders `TMG=1` y `ramps.json={}` con datos reales
de Paratec, sin tocar la topología del modelo.

1. Crear `app/data/paratec.py` con:
   - `fetch_thermal_plant_detail(plant_id)` → cachea JSON de `ThermalPlant.getThermalPlantDetail`
   - `reduce_to_config_params(plant_detail, config_number)` → `{TMG, RU, RD, Pmax, Pmin}` para UNA configuración (la activa/principal)
   - La heurística de selección: tomar la configuración con mayor `maximumAvailability` como la "principal" (proxy de la configuración más comúnmente despachada)
2. Modificar `case_builder.py`:
   - Si el JSON de Paratec existe en cache para la fecha, derivar TMG/ramps de él
   - Si no, caer al comportamiento actual (`parametros_plantas.csv` + `ramps.json`)
3. Test: smoke test existente (`tests/fixtures/xm_smoke/`) debe pasar sin cambios
   (sin Paratec cacheado, cae al comportamiento legacy)

### Fase B — Modelo por configuraciones (cambio de modelo)

1. Extender `case_builder.py`:
   - Para cada planta térmica, generar recursos `{plant_name}_cfg_{N}` para cada
     configuración N
   - Armar `excluded_configs[plant] = [cfg_1, cfg_2, ...]` (mapeo planta → lista de
     sus configuraciones)
   - Cada configuración recibe sus propios `TMG`, `RU`, `RD`, `Pmax`, `Pmin`, `beta`
2. Agregar restricción de exclusividad en `app/model/constraints/thermal/`:
   ```python
   def configuration_exclusivity_rule(model, plant_cfgs, t):
       return sum(model.z[cfg, t] for cfg in plant_cfgs) <= 1
   ```
3. Actualizar `UnitCommitmentModel._create_sets` para aceptar el nuevo conjunto
   `plant_configs` y la restricción de exclusividad
4. Tests: extender el smoke test con un caso de 2 configuraciones por planta

### Fase C — TMP (mínimo tiempo offline)

El modelo actual no tiene restricción de tiempo mínimo apagado (`min_down_time`).
Paratec puede exponerlo vía `minStopTime` o similar. Agregarlo es un cambio de modelo
separado que completa la representación de restricciones temporales de unidades
térmicas.

## 5. Lo que NO cambia

- **Solver**: `cbc` sigue siendo el default (ver `.agents/rules/python-patterns.mdc`).
- **Convención de índices**: `G` (fuel-fired generators) ⊆ `I` (todos los generadores).
  Las configuraciones heredan esta misma pertenencia.
- **Representación de presas y recursos no-térmicos**: sin cambios (set `I \ G`).
- **BESS**: sin cambios.
- **Ciclo combinado**: la representación actual de CC sigue funcionando; las
  configuraciones de CC ya son recursos separados con `exclude_resource_rule`. No
  se duplica ni se reemplaza ese mecanismo.
- **`parametros_plantas.csv`**: se mantiene como fallback hasta que la Fase A esté
  completa y validada. No se elimina sin un plan de migración explícito.

## 6. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| `maximumAvailability` de Paratec con unidades distintas a `dispo_declarada.csv` (kW) | Verificar contra datos conocidos (mismo procedimiento que el gotcha de revenue BESS 1000x en Fase 1). Agregar test de unidades. |
| Endpoints de Paratec no disponibles o con formato cambiado | La Fase A cae a comportamiento legacy (`parametros_plantas.csv`). La Fase B requiere Paratec → error claro si no hay datos, no silencio. |
| Explosión de variables binarias (N plantas × M configuraciones) | El número de configuraciones por planta es típicamente 2-4 (ej. "1 TV", "2 TV"). Con ~30 plantas térmicas, son ~60-120 recursos en G, comparable al tamaño actual del modelo (~50 generadores en I). No es un problema de escala. |
| `score_cutoff=70` del fuzzy matching falla con nombres de configuración | Los nombres de configuración se generan algorítmicamente (`{plant}_{cfg_N}`), no dependen de fuzzy matching. |
| `minGenerationTime` de Paratec en unidades distintas a horas | Verificar durante la Fase A. Si está en minutos, convertir a horas (redondear hacia arriba: `ceil(minutos / 60)`). |

## 7. Referencias

- Issue #26 (este documento)
- `docs/superpowers/specs/2026-08-06-ingesta-storage-xm-design.md` sección 7 — difirió
  explícitamente este diseño
- `.agents/rules/overview.mdc` — gotchas verificados (unidades, thefuzz, layout)
- `.agents/rules/python-patterns.mdc` — pydantic v2, Storage, solver cbc
- Memoria `project_thermal-configuration-dispatch`
