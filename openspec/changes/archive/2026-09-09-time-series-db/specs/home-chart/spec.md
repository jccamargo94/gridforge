# Delta para home-chart

> Nota de supersede (para sdd-archive): el cambio `time-series-db` deja obsoleto el
> supuesto "Backend `GET /chart/series` dado y congelado" y el no-objetivo "cambio
> backend" del Proposito/No objetivos de `openspec/specs/home-chart/spec.md`. Al
> archivar, actualizar esa narrativa (no hay requirement que reemplazar); los
> requirements de frontend existentes permanecen vigentes y se les agregan los
> siguientes.

## ADDED Requirements

### Requirement: REQ-HC-01 Promedio diario derivado de hourly_series

El backend `GET /chart/series` SHALL derivar el promedio diario de cada serie de precios desde la tabla `hourly_series` (unica fuente de verdad) en lugar de colapsar CSVs por request. El promedio diario de un (serie, dia) SHALL ser la media de las 24 filas horarias de la fuente ganadora del dia (mismo criterio de prioridad de run que hoy: ideal liquidado > provisional > preideal).

#### Scenario: SCN-HC-01-01 Promedio diario consistente con lo horario

- GIVEN 24 filas horarias publicas de `bolsa_tx1` para el dia D
- WHEN se pide `GET /chart/series` para D
- THEN el valor diario de `bolsa_tx1` es la media de las 24 filas

#### Scenario: SCN-HC-01-02 Dia sin datos no inventa ceros

- GIVEN dia D sin filas en `hourly_series` para una serie
- WHEN se pide `GET /chart/series` para D
- THEN esa clave queda `null` (gap), nunca cero

### Requirement: REQ-HC-02 Valores horarios disponibles

El backend SHALL exponer los valores horarios (hasta 24 por dia) de las series de precios servidas al Home, publicas y por tenant, manteniendo el contrato diario existente (claves, `days` 1..90). Valores horarios de otra fuente que no sea `hourly_series` SHALL NOT servirse.

#### Scenario: SCN-HC-02-01 Respuesta horaria publica

- GIVEN 24 filas publicas de `mpo_xm` para el dia D
- WHEN se piden los valores horarios de D
- THEN la respuesta expone 24 valores horarios mas el promedio diario

#### Scenario: SCN-HC-02-02 Aislamiento por tenant

- GIVEN filas publicas y filas del tenant A en `hourly_series`
- WHEN un miembro de A pide los valores horarios
- THEN recibe filas publicas y de A; ninguna fila de otro tenant
