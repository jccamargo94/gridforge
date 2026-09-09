# Propuesta: time-series-db (series horarias)

## Intento

Reemplazar el serving diario (promedio diario calculado en cada request desde `data/`) por una tabla angosta de series **horarias** reales `(ts, tenant_id, series_key, value, source)`, escrita por los dos writers existentes y servida por `chart.py` como valores horarios — no promedios diarios. Gráficas públicas (`tenant_id IS NULL`) y por tenant (`tenant_id` → FK a `tenants`). El driver es el **modelo de acceso** (aislamiento tenant + un único serving path), no el volumen (~4.4M filas/año).

## Alcance

### Dentro
- Tabla `tenants` (org/workspace) + membresía `tenant_members` (user↔tenant) + migración Alembic `0007`.
- Tabla `hourly_series` (FK `tenant_id` → `tenants.id`, `NULL` = público) + índice `(tenant_id, series_key, ts)` + migración Alembic `0008`.
- Upsert horario en `refresh_tick` (externals `bolsa_tx1`, `mpo_xm`).
- Upsert horario en el cierre de run para `ideal_marginal_price` (24 filas por run).
- Serving path horario en `chart.py` (público + por tenant), reemplazando el `pd.read_csv` por request.
- Tarea de backfill one-time desde los CSVs históricos de `data/`.

### Fuera
- TimescaleDB, pg_partman, particionado nativo, RLS/PostgREST (en este cambio).
- Rediseño de la gráfica Home (se habilita horario, no se fuerza el cambio visual).

## Capacidades

> Contrato con sdd-spec. Investigado `openspec/specs/`.

### Nuevas
- `hourly-series`: almacenamiento + ingesta horaria (dos writers) + backfill + serving horario con filtro por tenant.

### Modificadas
- `home-chart`: el backend `GET /chart/series` deja de estar "dado y congelado"; el promedio diario pasará a derivarse de la tabla horaria (única fuente de verdad) y `overlay horario` deja de ser no-objetivo.

## Enfoque

Opción A (cerrada en exploración): tabla plana Postgres indexada `(tenant_id, series_key, ts)`, serving app-layer en FastAPI. El tenant es una tabla `tenants` con membresía `tenant_members` user↔tenant resuelta en app-layer desde el JWT `user_id` (no PostgREST); `tenant_id IS NULL` = público. Sin particionado ni RLS. `source` lleva `run_id` para las series simuladas (preserva el drill-down `*_run_id`).

## Decisión cerrada (producto)

**`tenant_id`**: el usuario confirmó **tabla `tenants` nueva** (org/workspace) con membresía user↔tenant. `tenant_id` es FK a `tenants.id`; `NULL` = público. La auth sigue siendo JWT app-layer (Supabase = Postgres alojado + emisor JWT, sin RLS/PostgREST); la membresía se resuelve en app-layer a partir del `user_id` (`payload["sub"]`, `auth.py:33`). Decisión registrada en memoria (topic `sdd/time-series-db/tenant-model`).

## Invariantes de unidades (obligatorio)

| Serie | Unidad en tabla |
|-------|-----------------|
| `bolsa_tx1` | COP/MWh (precio_bolsa raw COP/kWh `*1e3`, `loaders.py:55`) |
| `mpo_xm` | COP/MWh (parse_mpo ya en COP/MWh) |
| `ideal_marginal_price` | COP/MWh (`results.py`) |
| cantidades (despacho) | MW |

Prohibido: mezclar raw kW / COP-per-kWh en la tabla (clase de bug 1000x ya ocurrido en Fase 1). La conversión se hace **en el writer**, no en el reader.

## Áreas afectadas

| Área | Impacto | Descripción |
|------|---------|-------------|
| `app/db/models.py` + `alembic/versions/0007` | Nuevo | Tablas `tenants` + `tenant_members` (membresía user↔tenant) |
| `app/db/models.py` + `alembic/versions/0008` | Nuevo | Tabla `hourly_series` + índice (FK `tenant_id` → `tenants.id`) |
| `app/scheduler/refresh.py` (`refresh_tick`) | Modificado | Upsert horario de externals |
| `app/db/queries.py` (`finish_run_ok`) | Modificado | Upsert 24 filas `ideal_marginal_price`; hook exacto: `executor.execute_run` (`executor.py:98-102`) → `finish_run_ok` (`queries.py:88`) |
| `services/api/chart.py` | Modificado | Leer de la tabla (horario) en vez de `pd.read_csv` + colapso diario |
| `app/db/queries.py` (read) | Nuevo | Query horaria filtrada por tenant |
| Backfill (tarea) | Nuevo | One-time desde CSVs de `data/` |

## Riesgos

| Riesgo | Prob | Mitigación |
|--------|------|------------|
| Doble escritura inconsistente (gap/stale) | Med | Upsert idempotente `ON CONFLICT (tenant_id, series_key, ts, source)`; helper compartido por ambos writers |
| Deriva de unidades (1000x) | Alta | Invariantes explícitas + test dorado por serie |
| Backfill incompleto (historia solo en CSVs) | Med | Tarea one-time validada contra fixture `xm_smoke` |
| Membresía tenant mal resuelta en app-layer | Med | Resolver tenant desde el JWT `user_id`; test de aislamiento público vs tenant |

## Rollback

Revertir `0008` (drop `hourly_series`) y luego `0007` (drop `tenants`/`tenant_members`); revertir writer + serving. La tabla es aditiva (no reemplaza los CSVs fuente), por lo que revertir = dejar de leer/escribir la tabla sin pérdida de datos.

## Dependencias

Ninguna externa. Reusa SQLAlchemy/Alembic y el JWT app-layer existente.

## Criterios de éxito

- [ ] El endpoint horario devuelve 24 valores/día públicos y por tenant.
- [ ] `refresh_tick` y el cierre de run escriben en `hourly_series` sin gaps para `xm_smoke`.
- [ ] Test dorado confirma COP/MWh (precios) y MW (cantidades) — sin clase 1000x.
- [ ] Backfill puebla historia; la gráfica histórica no arranca vacía.
