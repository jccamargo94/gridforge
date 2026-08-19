# Scraper de topología PARATEC → NodalNetwork — diseño

Fecha: 2026-08-19
Rama: `fase6b-topologia-paratec`

## Contexto

El modelo nodal del repo (`app/nodal/`) necesita una red de transmisión real del SIN
para producir LMPs creíbles: nodos (subestaciones), ramas (líneas), generación asociada
a nodos y demanda por nodo. Hoy el único network disponible es el ejemplo sintético
(`app/nodal/data/example_zonal_network.json`, 3 zonas) — útil para el pipeline, inútil
para análisis real.

XM publica estos datos en el portal PARATEC (`https://paratec.xm.com.co`), un
single-spa Angular con un backend JSON accesible sin autenticación
(`https://paratecbackend.xm.com.co/<servicio>/api`). Este spec diseña un scraper que
consume esos endpoints y construye un archivo `NodalNetwork` válido contra el schema
existente (`app/nodal/network/schemas.py`), listo para `run_nodal`.

**Fuera de alcance, deliberadamente**:
- Calibración/validación de los LMP resultantes contra precios nodales reales de XM —
  el pipeline de comparación nodal no existe todavía.
- Modelado AC completo (P, Q, V, pérdidas): el schema nodal es DC (`reactance`,
  `rating`); el scraper entrega exactamente eso.
- Fronteras internacionales (Ecuador138/230, Venezuela_*): aparecen en el dDEM con
  demanda 0 y se excluyen de las zonas.
- Modelado de transformadores como ramas: `PowerTransformer/PowerTransformerInfo`
  existe y se documenta como fuente futura, pero el schema `Branch` actual no tiene
  turn ratio; se deja fuera del v1.
- Autenticación/API keys: los endpoints probados responden con headers mínimos
  (`accept`, `origin`, `referer`, `user-agent`).

## 1. Datos verificados en vivo (2026-08-19, no asumido)

Todos los endpoints respondieron HTTP 200 con datos reales, probados con el recipe
canónico (curl con `accept: application/json` + `origin: https://paratec.xm.com.co` +
`referer: https://paratec.xm.com.co/` + `user-agent: Mozilla/5.0`).

| Fuente | Endpoint | Volumen | Contenido clave |
|---|---|---|---|
| Subestaciones | `reportetransmision/api/Substation/SubstationInfo` | 509 | nombre, kV, subAreaName, lat/long, department, municipality, voltageLevel[] |
| Barras | `reportetransmision/api/BarSections/getAll` | 1000+ | buses físicos por subestación/nivel |
| Líneas | `reportetransmision/api/Line/getAll` | 805+ | reactance, endurance, susceptance, thermalLimit (A), ratedVoltage (kV), length (km), subStation "ORIGEN - DESTINO", subArea |
| Generación catálogo | `reportegeneracion/api/NetEffectiveCapacities/getNetEffectiveCapacity` | 1 objeto jerárquico | por tipo de planta → elementos con elementName, netEffectiveCapacity, operator, municipality, department, subArea, fpoDate |
| Térmicas fuel | `reportegeneracion/api/ThermalPlant/getAllFuel` | 103 | fossilFuelType, netEffectiveCapacity (MW), heatRate (a menudo null) |
| Hidros | `reportegeneracion/api/HydraulicPlant/HydraulicPlantInfo` | 164 | netEffectiveCapacity, lat/long, subArea, hydraulicUnits[] |
| Solar | `reportegeneracion/api/SolarPlant/getAll` | 351 | netEffectiveCapacity, ratedPower, connectionVoltage |
| Eólico | `reportegeneracion/api/WindPlant/WindPlantInfo` | 3KB | pocas plantas |
| Demanda despacho | `api-portalxm.../DESPACHO/<yyyy-mm>/dDEM<mmdd>.txt` | 23 filas | `SubArea <nombre>,<24 valores MWh/h>` |
| Demanda pronóstico | `api-portalxm.../DEMANDAS/Pronostico Oficial/<yyyy-mm>/PRON_AREAS<mmdd>.txt` | 432 filas | `Sub<nombre>,<hora>,<EN|POT>,<7 días>` |

**Hallazgo de join (verificado)**: los 21 nombres de subárea del API de PARATEC
(`SubArea Valle`, `SubArea Bogota`, ...) matchean **exacto** con las 21 subáreas del
dDEM (el dDEM agrega `Ecuador138` y `Total`, ambos excluibles). El join
generación/subestación ↔ demanda por subárea es limpio, sin fuzzy matching.

**Hallazgo de backend (verificado)**: los endpoints de mapa viven en
`mapas/api/TransmissionMap/{getMarkers,getLines}` (442 markers, 805 líneas GeoJSON) —
no en `reportetransmision` (404 allí). No son necesarios para el v1 porque
`SubstationInfo` ya trae coordenadas y `Line/getAll` ya trae la reactancia, pero se
documentan como fuente alternativa/validación.

## 2. Arquitectura

Paquete nuevo `app/data/topology/` (paralelo a `app/data/download.py` — el scraper es
ingesta, no pertenece a `app/nodal/`):

```
app/data/topology/
  __init__.py
  fetch.py      # descarga PARATEC + dDEM/PRON via storage; sin open() directo
  parse.py      # normaliza JSON/txt a dataclasses internas
  build.py      # arma NodalNetwork (pydantic) desde los parsed
  cli.py        # comando Typer scrape-topology (registrado en app/cli.py)
```

Reglas del repo que se respetan:
- Toda I/O vía `app.storage.get_storage(root)` (como `download.py`), nada de `open()`
  directo excepto el patrón ya documentado.
- Pins y convenciones pydantic v2; cliente HTTP: **`httpx` (==0.28.1, ya en el
  lock)** — no se agregan dependencias nuevas.
- Fixtures de test anclados con `Path(__file__).parent`; CSV bajo
  `tests/fixtures/**/*.csv` ya exceptuado del `.gitignore`.

### 2.1 fetch.py

- `fetch_substations()`, `fetch_lines()`, `fetch_generation_catalog()`,
  `fetch_thermal_fuel()`, `fetch_hydro()`, `fetch_solar()`, `fetch_wind()` — cada uno
  hace GET al endpoint PARATEC con los headers canónicos y devuelve el JSON (list o
  `{header, data}`).
- `fetch_ddem(date)`, `fetch_pron_areas(date)` — construyen la ruta
  `M:/InformacionAgentes/Usuarios/Publico/DESPACHO/<yyyy-mm>/dDEM<mmdd>.txt` (y el
  análogo para PRON) y descargan vía el mismo mecanismo de `download.py`
  (`api-portalxm.xm.com.co/administracion-archivos/ficheros/descarga-archivo?ruta=...`).
- Cache en `data/topology/raw/` (git-ignored por `data/`) para no re-descargar en
  cada corrida; flag `--refresh` para forzar.

### 2.2 parse.py

Normaliza a dataclasses internas:
- `SubstationRef(name, subarea, base_kv, lat, long, department, municipality)`
- `LineRef(name, from_sub, to_sub, reactance, rating_a, kv, length_km, subarea)`
- `GenRef(name, plant_type, capacity_mw, subarea, operator, fuel, heat_rate, lat, long)`
- `DemandSeries(subarea, values_24h: list[float])`

Conversiones verificadas/explícitas:
- `Line/thermalLimit` viene en **amperios**; rating en MW ≈
  `thermalLimit * kV * sqrt(3) / 1000` (DC aproximación; documentar en el código).
- `Line/subStation` es `"ORIGEN - DESTINO"` con el separador `" - "` (verificado:
  `"AGUABLANCA - ALFEREZ II"`); split por el primer separador.
- `heatRate` suele ser null → marginal_cost por combustible con tabla fallback
  documentada (carbón/gas/ACPM), no inventada en silencio.

### 2.3 build.py

Arma `NodalNetwork` (schema de `app/nodal/network/schemas.py`):

- **zones** = subestaciones con `base_kv` = nivel de tensión principal de
  `voltageLevel[]` (mayor kV). Conserva jerarquía en metadata
  (`area → subarea → subestación`) para permitir agregar el modelo a nivel subárea/área.
- **generators** = elementos del catálogo de generación con `netEffectiveCapacity > 0`,
  cruzados con fuel/hydro/solar para completar tipo y coordenadas:
  - `p_max` = netEffectiveCapacity (MW)
  - `marginal_cost` = derivado de heat_rate × precio combustible (fallback por fuel)
  - `zone` = subestación de su subárea: primero match por subárea (exacto), luego
    cercanía geográfica por lat/long dentro de la subárea (misma lógica de la
    discusión de diseño: "generador al nodo más cercano").
  - hidros: asignar a la subestación más cercana por coordenadas (tienen lat/long).
- **branches** = líneas con `from_zone`/`to_zone` = subestaciones origen/destino
  (match por nombre exacto contra zones; si una subestación no existe como zona, crear
  zona implícita o dropear la rama con warning — decisión v1: dropear con log).
- **loads/demand_shares** = desde dDEM (despacho real) o PRON (pronóstico):
  - subárea → distribución a subestaciones dentro de la subárea por share de
    capacidad instalada (default) o uniforme (`--demand-split capacity|uniform`).
  - `loads` = 24 valores por zona; `demand_shares` = share promedio normalizado que
    cubre exactamente todas las zonas y suma 1.0 (contrato del schema).
  - `Ecuador138`, `Ecuador230`, `Venezuela_*` excluidos (demanda 0 / frontera).
- Referencias colgantes: el validator del schema ya lanza `ValueError`; el builder
  debe fallar con mensaje que nombre la zona/rama culpable, no dejar que el validator
  sea la única defensa.

### 2.4 cli.py

```
uv run gridforge scrape-topology --date 2026-08-01 \
    --demand-source ddem|pron --demand-split capacity|uniform \
    --out data/topology/paratec_network_<date>.json [--refresh]
```

Salida: JSON `NodalNetwork` serializado + resumen en stdout (n zonas, n generadores,
n ramas, n subáreas, demand total).

## 3. Testing

- **Unit (parse)**: fixture mínimo con 2–3 líneas, 2 subestaciones, 1 generador y un
  dDEM de 2 subáreas, anclado en `tests/fixtures/topology/` — valida split de
  `subStation`, conversión A→MW, join de subáreas exacto, exclusión de frontera.
- **Unit (build)**: mismo fixture → `NodalNetwork` válido: todas las referencias
  resueltas, `demand_shares` cubre todas las zonas y suma 1.0, `loads` tienen 24
  valores.
- **Integración (fetch)**: solo con `--live` (test marcado `@pytest.mark.live`, no
  corre por defecto — el repo ya tiene tests offline; no introducir red en la suite
  normal). Verifica que los endpoints reales responden 200 y que el catálogo trae
  >300 elementos.
- **Golden**: un `paratec_network.json` pequeño de referencia se commitea como fixture
  (patrón golden del repo, como pide `AGENTS.md` para `case_builder.py`).

## 4. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Nombres de subestación en `Line/subStation` no matchean exacto con `SubstationInfo` (abreviaturas) | v1: dropear con warning + reporte de no-resueltos; test unitario contra el fixture real capturado para medir el % de match |
| `heatRate` null en muchas térmicas → marginal_cost estimado | tabla fallback por fuel explícita y documentada; el resultado es académico, no de mercado |
| dDEM/PRON cambian de layout | parser tolerante (split por coma, filas `Total`/frontera ignoradas), validado contra archivos reales capturados |
| PARATEC cambia API sin aviso | endpoints verificados en vivo hoy; cache en `data/topology/raw/` preserva la última corrida |
| Volumen: 509 zonas → ramas 805 con 2.3MB de bays no usados | solo se descargan los endpoints necesarios; bays/reactores/STATCOMs fuera de alcance v1 |

## 5. Entregables

1. `app/data/topology/{__init__,fetch,parse,build,cli}.py`
2. Registro del comando `scrape-topology` en `app/cli.py`
3. Tests + fixture golden en `tests/fixtures/topology/`
4. Documentación breve en `README.md` (sección de datos/topología)
</content>