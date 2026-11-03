# Disponibilidad declarada vs capacidad PARATEC (issue #84) - Diseno

Rama: `fase9d-dispo-vs-paratec`. Fecha: 2026-11-03.

## Que resuelve
Detectar inconsistencias entre la disponibilidad declarada por cada recurso
(`DispoDeclarada`, pydataxm) y su capacidad efectiva neta publicada en PARATEC:
autochequeo del agente e inteligencia sobre patrones de indisponibilidad.

## Alcance recortado respecto del issue (y por que)
- **Solo capacidad efectiva neta.** El issue menciona tambien `technicalMinimum`
  de `ThermalPlant/getThermalPlantDetail`. Ningun payload del repo (codigo,
  fixtures, tests) muestra ese campo; una regla sobre un esquema no verificado
  seria especulativa. La capacidad efectiva neta si esta verificada: es el campo
  que `parse_generators` lee del catalogo `getNetEffectiveCapacity` y que el
  builder nodal usa como `p_max`.
- **Bajo demanda, sin job periodico ni persistencia de alertas.** El calculo es
  barato y determinista sobre los year CSVs; persistir alertas y programarlas
  queda para cuando se defina quien las consume.

## Crosswalk
Nombre de recurso XM (`ListadoRecursos`) <-> `elementName` de PARATEC por nombre
normalizado exacto (minusculas, sin tildes ni puntuacion). Sin fuzzy: una planta
equivocada es peor que una sin cruzar. Se reportan cobertura (`match_rate`),
recursos sin cruce y nombres PARATEC ambiguos (omitidos). La cobertura real
esta sin medir: los nombres de PARATEC pueden diferir de los de XM (p. ej.
prefijos como `H_` en fixtures), por lo que el cruce puede ser parcial.

## Reglas (parametros explicitos y devueltos en la respuesta)
- `exceeds_capacity`: pico diario declarado (MW) > capacidad x (1 + `over_tol`, 2%).
- `persistent_low`: >= `min_days` (3) dias seguidos con pico diario < `low_pct`
  (50%) de la capacidad y > 0. Los dias con disponibilidad 0 se cuentan aparte
  (`outage_days`: señal de mantenimiento/salida, no de inconsistencia).
- `hour_pattern`: horas con disponibilidad 0 en >= 80% de los dias con
  disponibilidad (>= 5 dias activos).
Unidades: `dispo` kW -> MW (x1e-3, como `case_builder.py`); capacidad en MW.

## API / UI
`GET /market/availability-check?start=&end=&low_pct=&min_days=&over_tol=`
(rango <= 92 dias). 404 si falta el CSV del ano o la capacidad cacheada
(`topology/raw/capacity.json`, la escribe el scrape de topologia). Pagina
`/availability` con tabla de alertas por recurso y cobertura del cruce.

## Limites
Sin validar contra datos reales de XM/PARATEC (fixture sintetico y datos
armados). Las plantas rivales aparecen por nombre: la disponibilidad declarada
es informacion publica de XM (a diferencia de las ofertas, ver #82).
