# Especificacion hourly-series

## Proposito

Series horarias reales (24 valores/dia) en tabla angosta Postgres: escritas por `refresh_tick` (externals) y el cierre de run, servidas por `chart.py` como unica fuente de verdad, con aislamiento publico (`tenant_id NULL`) vs por-tenant.

## Requirements

### Requirement: REQ-HS-01 Esquema de series horarias

El sistema SHALL crear via Alembic `0007` las tablas `tenants` y `tenant_members` (membresia user↔tenant, resuelta en app-layer desde el JWT `user_id`) y via `0008` la tabla `hourly_series` (`ts`, `tenant_id` FK → `tenants.id` con `NULL` = publico, `series_key`, `value`, `source`) con indice `(tenant_id, series_key, ts)`. La escritura SHALL ser idempotente sobre `(tenant_id, series_key, ts, source)`.

#### Scenario: SCN-HS-01-01 Migraciones aplicadas

- GIVEN base sin migrar
- WHEN se aplican `0007` y `0008`
- THEN existen `tenants`, `tenant_members`, `hourly_series` con FK e indice

#### Scenario: SCN-HS-01-02 Upsert de fila publica repetida

- GIVEN fila publica `(ts, bolsa_tx1, v, source)` ya escrita
- WHEN se re-escribe la misma clave
- THEN el valor se actualiza sin fila duplicada

### Requirement: REQ-HS-02 Ingesta de externals horarios

`refresh_tick` SHALL upsertar `bolsa_tx1` y `mpo_xm` como filas horarias publicas (24/dia, hora Bogota) cuando XM las publique; horas sin publicacion SHALL quedar ausentes (gap), nunca cero.

#### Scenario: SCN-HS-02-01 Dia completo publicado

- GIVEN XM publico las 24 horas de un dia
- WHEN corre refresh_tick
- THEN existen 24 filas por serie, publicas, en hora Bogota

#### Scenario: SCN-HS-02-02 Re-tick del mismo periodo

- GIVEN refresh_tick ya corrio para el dia D
- WHEN corre de nuevo para D
- THEN el total por (serie, dia) sigue en 24, sin duplicados ni huecos

### Requirement: REQ-HS-03 Ingesta al cierre de run

Al completar un run (`finish_run_ok` / `finish_nodal_run_ok` via executor), el sistema SHALL upsertar 24 filas `ideal_marginal_price` desde su `price_path`, con `source` = `run_id`. Runs publicos SHALL escribirse con `tenant_id NULL`; runs no publicos SHALL NOT escribirse como publicos, y SHALL escribirse bajo el tenant del owner solo si su membresia es resoluble.

#### Scenario: SCN-HS-03-01 Run publico diario

- GIVEN run publico `done` con price_path de 24 valores
- WHEN se ejecuta el hook de cierre
- THEN existen 24 filas `ideal_marginal_price`, `source=run_id`, `tenant_id NULL`

#### Scenario: SCN-HS-03-02 Run privado sin fuga publica

- GIVEN run privado cuyo owner no pertenece a ningun tenant
- WHEN se completa el run
- THEN ninguna fila de ese run se escribe con `tenant_id NULL`

### Requirement: REQ-HS-04 Invariantes de unidades

Todo `value` de precio SHALL persistirse en COP/MWh y toda cantidad en MW; la conversion (COP/kWh x1e3, kW→MW) SHALL ocurrir en el writer antes de persistir, nunca en el reader. Tests dorados por serie SHALL fallar si una escala cruda (clase 1000x) entra a la tabla.

#### Scenario: SCN-HS-04-01 Precio almacenado en COP/MWh

- GIVEN fuente raw COP/kWh (`precio_bolsa`)
- WHEN refresh_tick persiste la serie
- THEN `value` en la tabla es COP/MWh (x1e3), no COP/kWh

#### Scenario: SCN-HS-04-02 Test dorado detecta escala cruda

- GIVEN fila con valor fuera de unidad (kW o COP/kWh)
- WHEN corre el test dorado de la serie
- THEN la verificacion falla (invariante violada)

### Requirement: REQ-HS-05 Serving horario desde la tabla

`chart.py` SHALL leer de `hourly_series` (sin `pd.read_csv` + colapso por request), exponer valores horarios (hasta 24/dia) con promedio diario derivado de la tabla y preservar `source` (= `run_id`) para el drill-down. El reader SHALL filtrar filas publicas para todo usuario autenticado y filas de los tenants del usuario via membresia; filas de otro tenant SHALL NOT ser visibles.

#### Scenario: SCN-HS-05-01 Respuesta horaria de 24 valores

- GIVEN 24 filas publicas `bolsa_tx1` de un dia
- WHEN un usuario autenticado pide la serie
- THEN recibe 24 valores horarios mas el promedio diario derivado

#### Scenario: SCN-HS-05-02 Aislamiento publico vs tenant

- GIVEN filas publicas, de tenant A y de tenant B
- WHEN un miembro de A pide la serie por tenant
- THEN ve filas publicas y de A; ninguna de B

### Requirement: REQ-HS-06 Backfill historico one-time

El sistema SHALL incluir una tarea one-time que pueble `hourly_series` desde los CSVs historicos de `data/` con las conversiones e invariantes de REQ-HS-04, idempotente y validada contra `xm_smoke`, para que la grafica historica no arranque vacia.

#### Scenario: SCN-HS-06-01 Backfill correcto

- GIVEN CSVs historicos en `data/`
- WHEN corre la tarea de backfill
- THEN cada (serie, dia) historico queda con 24 filas en la unidad correcta

#### Scenario: SCN-HS-06-02 Backfill re-ejecutado

- GIVEN la tarea ya corrio sobre el rango R
- WHEN se re-ejecuta sobre R
- THEN el conteo de filas no cambia (sin duplicados)
