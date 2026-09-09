# Ejecución diaria automática de corridas (ideal/preideal/LMP) — Diseño

Rama: `fase7a-daily-automation` (a crear). Repo: `gridforge`, `develop`.
Fecha: 2026-09-08.
Issue: #89 (backend). #90 (frontend Home) queda fuera de alcance, con su
discusión cerrada en este diseño: el Home será una serie de tiempo continua
de precios con drill-down por día; la pestaña "corridas" queda solo para
corridas manuales.

## 1. Contexto

Hoy todo run se dispara manualmente desde la UI (`POST /runs`), con `user_id`
NOT NULL y visibilidad estrictamente por usuario. No hay scheduler ni
mecanismo de refresco: los year CSVs (`dispo_declarada_{year}.csv`,
`ofertas_{year}.csv`, `demaCome_{year}.csv`, `precio_bolsa_{year}.csv`,
`dispo_come_{year}.csv`) se descargan una sola vez por año
(`ensure_bulk_data_for_year`, one-shot `if storage.exists(path): return`)
y quedan stale (al 2026-09-08 el más reciente tiene datos hasta 2026-08-11).

`case_builder.build_case` filtra esos year CSVs por fecha (`datetime.dt.date
== dispatch_date`): un CSV stale no produce un error, produce un día vacío
silencioso o caídas a heurísticas con WARNING. Correr "el modelo de hoy" sin
refresco incremental es, hoy, imposible.

Evidencia de publicación XM (medida contra el endpoint de listado
`api-portalxm.xm.com.co/administracion-archivos/ficheros`, 2026-05..09):

- Todo el paquete de archivos por-fecha del día D se publica en **D-1** en
  tres oleadas: OFEI ~08:05–08:40; PrId + iMAR ~09:00–13:40 (iMAR admite
  modificaciones hasta ~165 min después); familia DESPACHO
  (dCondIniU/dCondIniP/dAGCUNIDAD) ~14:00–14:30, escritura única.
- El precio real de bolsa (TX1, PrecBolsNaci, serie anual
  `precio_bolsa_{year}.csv`) se publica **2–4 días después** de D.
- Las series reales comerciales demaCome/dispo_come se publican con ~3 días
  de rezago; las ofertas reales (PrecOferDesp, `ofertas_{year}.csv`) se
  publican por mes calendario completo, ~1° del mes siguiente.
- El nivel `ideal` NUNCA lee dDEM: sus insumos reales son demaCome +
  dispo_come + PrecOferDesp, todos con rezago. Para fechas recientes
  `build_case` cae con WARNING sonoro a pronóstico PrId (demanda) y
  disponibilidad declarada (Pmax).

Decisión de producto (dos corridas por fecha, separadas y comparables):
correr temprano con insumos pronosticados (provisional) y volver a correr
cuando existen los insumos reales (settled). La diferencia provisional vs
settled aísla el error de los insumos pronosticados; settled vs XM aísla el
error del modelo. Ambas quedan públicas y etiquetadas.

## 2. Alcance (#89 — backend solamente)

Dentro de alcance:

- Tabla `run_plans` + scheduler de planes dentro del worker existente
  (sin servicio nuevo, sin cron externo, sin tokens de servicio).
- Refresco incremental de datos: pull diario por ventana de las 5 series
  reales + upsert a los year CSVs; estado rodante de precios de oferta
  (real manda; estimación MPO actualiza y se reutiliza).
- Dos carriles por fecha: provisional (temprano) y settled (cuando llegan
  los reales; batch del mes cerrado + `lmp_settled` por TX1).
- Reevaluación de métricas sin re-solve (`reevaluate_metrics`) contra la
  referencia final: iMAR(D) definitivo para preideal, bolsa TX1(D) para
  ideal.
- Visibilidad pública: `runs.user_id` nullable, `runs.visibility`
  private|public, gates de list/detail/artefactos.
- Endpoint nuevo `GET /chart/series` (contrato en §7).
- Migración Alembic, tests, config por env vars.

Fuera de alcance (deliberado):

- Frontend Home y su gráfica (#90, spec/plan propio después de mergear #89).
- Infraestructura de alertas externas (solo plan status + log del run).
- PrecOferDesp en tiempo real (XM no la publica; el mes cerrado es la
  fuente de verdad de ofertas).
- Cambios al flujo de corridas manuales existente.
- Series lmp en `/chart/series` v1.

## 3. Modelo de datos

### 3.1 Tabla nueva `run_plans`

| columna | tipo | notas |
|---|---|---|
| id | uuid PK (hex, patrón repo) | |
| kind | str | dominio cerrado, ver §4 |
| target_date | Date | día objetivo del plan |
| status | str | pending \| running \| done \| skipped \| failed |
| attempts | int default 0 | reintentos dentro de ventana |
| due_at | timestamptz | próxima ventana de intento (UTC) |
| run_id | FK runs.id nullable | run producido (done/failed) |
| error | text nullable | motivo de failed/skipped |
| created_at / started_at / finished_at | timestamptz | tz-aware UTC, patrón repo |
| **UNIQUE(kind, target_date)** | | dedupe a nivel esquema; reintento = re-claim de la misma fila |

Semántica de status: `pending` aguarda su ventana/insumos; `running` reclamado
por el worker; `done` su run_id está done; `skipped` ventana vencida sin
insumos (con motivo); `failed` intentos agotados o error de ejecución (con
motivo). Un plan `pending` viejo es evidencia auditable de una noche que el
worker no intentó (reconciliación por tabla, no por dedupe en código).

### 3.2 Cambios en `runs`

- `user_id`: pasa a NULLABLE. Un run sin user_id es un run de sistema
  (generado por plan); un run manual siempre tiene user_id.
- `visibility`: str default `private`; valores `private|public`. Los runs de
  planes diarios nacen `public` (lectura para cualquier usuario logueado);
  los manuales siguen `private`.
- `input_grade`: str nullable `provisional|settled` (null en manuales).
  Etiqueta si la corrida usó insumos pronosticados o reales.

### 3.3 Cambios en `metric_set`

- `reference`: str `iMAR|bolsa_tx1` — contra qué se evaluaron las métricas.
- `evaluated_at`: timestamptz — cuándo se (re)evaluaron.

La reevaluación pisa la misma fila `metric_set` del run (run_id unique FK):
sin la columna reference, un re-eval posterior a TX1 sería indistinguible
del provisional contra iMAR.

### 3.4 Migración

Una migración Alembic: create `run_plans`, alter `runs.user_id` nullable,
add `runs.visibility`/`runs.input_grade`, add `metric_set.reference`/
`evaluated_at`. Backfill: runs existentes → `visibility=private`,
`input_grade=NULL`, `reference=NULL`.

## 4. Tipos de plan y ciclo diario

| kind | target_date | cuándo intenta | insumos requeridos | run creado |
|---|---|---|---|---|
| `preideal_daily` | D | ventana D-1 15:00–23:59 (Bogotá) | blobs de D (OFEI/PrId/dCondIniU/dCondIniP/dAGCUNIDAD/iMAR) + year CSVs con filas hasta D + estimación de ofertas para D | preideal, input_grade=provisional |
| `ideal_daily` | D | ventana D-1 15:00–23:59 | igual que preideal_daily | ideal, input_grade=provisional |
| `reeval_preideal` | D | earliest D-1 18:00 (default) | run preideal_daily(D) done + iMAR(D) sin modificaciones pendientes (ventana de mod ~165 min ya cerrada) | ninguno: re-evalúa metric_set del run |
| `reeval_ideal` | D | sweep 05:30 diario (2–4 días después de D) | run ideal_daily(D) done + fila TX1(D) presente en `precio_bolsa_{year}.csv` | ninguno: re-evalúa metric_set del run |
| `lmp_settled` | X | sweep 05:30 diario, creado al aparecer TX1(X) | TX1(X) + insumos reales de X + network nodal | lmp, input_grade=settled |
| `preideal_settled` | D ∈ mes M | gate mensual ~1°–2° de M+1 | ofertas reales del mes M completas en `ofertas_{year}.csv` | preideal, input_grade=settled |
| `ideal_settled` | D ∈ mes M | gate mensual ~1°–2° de M+1 | idem + demaCome/dispo_come del mes M | ideal, input_grade=settled |

Reglas de mapeo reeval → run fuente: `reeval_preideal(D)` apunta al run del
plan `preideal_daily(D)` (UNIQUE(kind,target_date) ⇒ resolución 1:1 vía
`run_plans.run_id`). Si el plan fuente falló/no existe, el reeval se marca
`skipped` con motivo.

Los `*_settled` de todos los días de M se crean como filas `run_plans`
independientes (mismo patrón claim que el resto) cuando el gate mensual
detecta el mes completo. La referencia de evaluación de los settled es
`bolsa_tx1`.

### 4.1 Semántica de las dos corridas

- **provisional** (preideal_daily/ideal_daily de D, corre en D-1): el
  "mercado de mañana". Insumos pronosticados: demanda PrId, disponibilidad
  declarada, ofertas estimadas por heurística. Es lo que el usuario ve el
  día antes y el mismo día.
- **settled** (corre cuando llegan los reales): insumos reales (demaCome,
  dispo_come, PrecOferDesp del mes cerrado) y referencia TX1. Es la corrida
  comparable contra XM.
- `lmp_settled(X)` no tiene versión provisional útil: se crea directo al
  aparecer TX1(X).

## 5. Refresco incremental y estado rodante de ofertas

### 5.1 Pull diario por ventana (las 5 series reales)

Reemplaza el one-shot anual de `ensure_bulk_data_for_year` por un pull
incremental por ventana (default últimos 7 días corridos, configurable) de
las 5 series vía pydataxm (PrecBolsNaci, DemaCome, DispoCome,
PrecOferDesp, DispoDeclarada), merge keyed y upsert a los year CSVs:

- Cada serie publica con su propio rezago; el pull diario simplemente no
  encuentra filas nuevas hasta que XM las publica (TX1 a D+2..4, demaCome/
  dispo_come a ~D+3, PrecOferDesp del mes M recién ~1° de M+1 — el mismo
  pull diario captura el mes cerrado sin job mensual aparte).
- Merge por clave (fecha+recurso+hour para per-recurso; fecha para sistema):
  filas existentes se sobreescriben, filas nuevas se agregan; el archivo se
  reescribe completo de forma atómica vía Storage.
- **Crítico**: los loaders de `app/data/loaders.py` están decorados con
  `functools.lru_cache(maxsize=16)`. Después de cada rewrite hay que
  invalidar la caché (`.cache_clear()` sobre los loaders afectados), o el
  mismo proceso worker seguiría leyendo el CSV viejo.

El pull corre como tick periódico del worker (default cada 60 min,
`DATA_REFRESH_INTERVAL_MINUTES`), no bloquea el claim de runs.

### 5.2 Estado rodante de precios de oferta (modelo m0075/m0078 aprobado)

Semántica aprobada: la extracción mensual real es la primera fuente de
verdad; si no está disponible para un recurso, se usan los valores más
recientes de la heurística (resolución MPO), guardados y reutilizados para
los días siguientes.

La heurística ya existe (`app/data/heuristic/biddings.py`:
`detect_marginal_resources` — recurso "a media máquina" en PrId con
eliminación iterativa; el recurso resuelto vale el MPO de esa hora; cache
por día en `ofertas_estimado/ofertas_estimado_{year}.csv`). Cambios
necesarios:

1. `ensure_ofertas_estimado` debe computar `ultimo_precio` sobre la **unión**
   de ofertas reales y estimadas (`real ∪ estimado`, ordenado por fecha;
   empate a igual recencia gana el real), no solo sobre las reales — así las
   resoluciones MPO de días previos se arrastran a los días siguientes.
2. El pull mensual real (5.1) alimenta esa unión con la fuente de verdad; el
   estado rodante emerge de la misma unión sin archivo nuevo.

## 6. Scheduler dentro del worker

`services/worker/main.py` mantiene su loop actual (claim de runs manuales,
POLL_INTERVAL_SECONDS=5, nunca crashea) y agrega ticks separados por
responsabilidad (sin anidar el claim):

1. **Manual lane**: `process_once` existente, intacto.
2. **Plan tick** (default cada 60 s, `PLAN_TICK_SECONDS`): para cada plan
   `pending` con ventana abierta (due_at ≤ now ≤ deadline, en
   America/Bogota), verifica el predicado de insumos del kind (§4); si está
   completo, claim (mismo patrón FOR UPDATE SKIP LOCKED postgres-only) y
   ejecuta: `_build_case` → `run_case` → `finish_run_ok`/`finish_nodal_run_ok`/
   `finish_run_failed`, igual que el camino manual; escribe `run_plans.run_id`,
   status done/failed, `attempts++` en fallo. Fallo → reintento en la
   próxima iteración dentro de la ventana hasta `PLAN_MAX_ATTEMPTS` (default
   3); ventana vencida sin insumos → `skipped` con motivo.
3. **Freshness tick** (§5.1).
4. **Sweeps** (05:30 default, config): `reeval_ideal` + creación de
   `lmp_settled(X)`/`reeval_preideal`/`reeval_ideal` para fechas que ganaron
   TX1 o iMAR final.
5. **Gate mensual**: cuando el pull detecta PrecOferDesp del mes M completo,
   crea las filas `preideal_settled`/`ideal_settled` de M.

Horarios y ventanas siempre en America/Bogota; `due_at`/timestamps se
guardan en UTC (tz-aware, patrón repo). Los ticks son funciones puras
testeables (`plan_tick(session, now)` etc.) con integración mínima en el
loop.

## 7. Visibilidad pública y API

- `create_case_and_run(...)`: `user_id` pasa a opcional; parámetros nuevos
  `visibility="private"` y `input_grade=None`. `POST /runs` (manual) no
  cambia de comportamiento.
- `GET /runs`: devuelve runs donde `user_id == me OR visibility == public`
  (los públicos van etiquetados como "Corridas del día"; el payload incluye
  `visibility` e `input_grade` para que la UI los agrupe). Orden: created_at
  desc.
- `GET /runs/{id}` y artefactos/descargas/log: permitidos al dueño o a
  cualquier usuario logueado cuando `visibility == public` (404 uniforme si
  no califica). No hay endpoints de edición/borrado de runs; los públicos
  son read-only por construcción.
- `run_plans` NO se expone por API en esta fase (auditable por plan status
  + logs del worker).

### 7.1 `GET /chart/series`

Query: `?days=30` (default 30, tope 90). Auth: cualquier usuario logueado.
Devuelve, por día calendario (America/Bogota), el promedio diario
COP/MWh de cada serie (media de las 24 horas), con `null` donde no hay
dato:

```json
[
  {
    "date": "2026-09-07",
    "bolsa_tx1": 1234.5,
    "mpo_xm": 1200.0,
    "ideal_settled": 1180.2,
    "ideal_settled_run_id": "…",
    "ideal_provisional": 1210.1,
    "ideal_provisional_run_id": "…",
    "preideal": 1190.7,
    "preideal_run_id": "…"
  }
]
```

Resolución de series (server-side, desde runs públicos done):

- `bolsa_tx1`: año CSV `precio_bolsa` (load_actual_bolsa por fecha).
- `mpo_xm`: iMAR(D) final (parse_mpo sobre el archivo por-fecha).
- `ideal_settled` / `ideal_provisional` / `preideal`: run público done del
  kind correspondiente con mayor precedencia — `preideal` = settled del día
  si existe, si no el provisional (`ideal_settled > ideal_provisional`,
  `preideal_settled > preideal_daily`); valor = media de
  `ideal_marginal_price` de su `price_path`.
- `*_run_id` acompaña a cada serie simulada para que #90 pueda deep-linkear
  al detalle del día.
- Fuera de alcance v1: series lmp, escenarios, bandas.

## 8. Configuración

Env vars (worker), todas con default:

| var | default | significado |
|---|---|---|
| `DAILY_ENABLED` | `true` | kill switch del scheduler |
| `SCHEDULER_TZ` | `America/Bogota` | zona de ventanas |
| `PLAN_TICK_SECONDS` | `60` | período del plan tick |
| `PLAN_MAX_ATTEMPTS` | `3` | reintentos por ventana |
| `PLAN_RETRY_MINUTES` | `15` | separación mínima entre reintentos |
| `DATA_REFRESH_INTERVAL_MINUTES` | `60` | período del freshness tick |
| `DATA_REFRESH_WINDOW_DAYS` | `7` | ventana del pull incremental |
| `SWEEP_TIME` | `05:30` | hora diaria de sweeps TX1 |
| `REEVAL_PREIDEAL_TIME` | `18:00` | earliest de reeval_preideal |
| `DAILY_EARLIEST` / `DAILY_DEADLINE` | `15:00` / `23:59` (D-1) | ventana de corridas frescas |

## 9. Fallos y visibilidad de fallos

- Plan fallido → `failed` + `error` legible; reintento re-claim con
  `attempts++` dentro de la ventana; ventana vencida sin insumos →
  `skipped` con motivo (lista cerrada: insumos no publicados, plan fuente
  fallido, mes incompleto).
- El run asociado queda `failed` con su log descargable; los huecos de días
  públicos son visibles como `null` en las series (un día sin dato se ve).
- Sin alertas externas en esta fase: la superficie es plan status + log del
  run + tabla `run_plans` auditable.

## 10. Testing

- `run_plans`: claim/reintento/dedupe (UNIQUE kind+target_date),
  claim concurrente (postgres-only), statuses y motivos.
- Visibilidad: list/detail/artefactos con runs privados ajenos, públicos y
  propios.
- Refresco incremental: merge keyed idempotente (pull repetido no duplica),
  invalidación de lru_cache de loaders, rewrite atómico.
- Estado rodante: unión real∪estimado con precedencia correcta.
- `reeval_*`: pisa metric_set con `reference`/`evaluated_at` correctos; no
  re-suelve.
- `/chart/series`: merge y precedencia con runs sintéticos.
- Extender fixtures `xm_smoke`: un mes cerrado sintético para el camino
  settled.
- El scheduler no corre en tests: ticks puros con reloj inyectado +
  integración mínima.

## 11. Rollout

Rama `fase7a-daily-automation` off `develop` → spec + plan → implementación
con tests verdes (`uv run pytest -q`, pre-commit ruff bloqueante) → PR contra
`develop`. No toca corridas manuales existentes. `DAILY_ENABLED` permite
desplegar apagado y prender después.

## 12. Decisiones registradas

- Dos corridas por fecha (provisional + settled) separadas y comparables
  (m0073); settled gatillado por la extracción real mensual (m0075/m0078).
- Tabla `run_plans` auditable (no dedupe por código) — elección del usuario.
- Ejecución por disponibilidad de insumos, no por hora fija; horas default
  derivadas de evidencia de publicación XM documentada (§1).
- Home de #90 = series continuas con drill-down; la lista queda solo para
  corridas manuales (m0081/m0083).
- `/chart/series` v1 = 5 series sin lmp.

## Enmienda 2026-09-09 (fix wave post-revisión final)

Decisiones de la revisión final de la rama, aprobadas por el dueño del spec
(rama `fase7a/w5-fix-final`; esta enmienda supera la nota de "nunca trae hoy"
del §5.1):

1. El extremo del pull del freshness tick llega al siguiente día calendario
   Bogotá: XM solo devuelve filas publicadas, así que el rezago de cada serie
   gobierna lo que llega, y la fila `dispo_declarada(D)` puede existir local
   durante la ventana D-1.
2. El freshness tick precarga los blobs por fecha del día siguiente desde
   `daily_earliest` (15:00 default): sin eso, el gate de insumos de las
   corridas frescas D-1 nunca se abre en un despliegue limpio.
3. Orden de ticks del worker: refresh antes de plan (un claim del mismo pase
   debe observar filas/blobs ya traídos por ese pase); sweep después de plan;
   el lane manual queda último, fuera del bloque diario.
4. `reeval_preideal` pasa a ventana abierta (cierra en None; abre D-1 a
   `reeval_preideal_time`): evalúa contra el iMAR final cuando corra — el
   blob iMAR(D) se fuerza-refresca antes de evaluar — y las filas curadas por
   el sweep quedan funcionales.
5. Reconciliación al boot del worker de filas `running` huérfanas por crash
   (asume worker single-process; un reaper por edad queda fuera de alcance
   para despliegues multi-worker).
6. `claim_next_pending_run` (lane manual) solo reclama runs con `user_id`: los
   runs de sistema (`user_id` NULL) se reclaman por id al crearse.
