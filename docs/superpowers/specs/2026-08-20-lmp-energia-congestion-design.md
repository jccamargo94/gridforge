# Spec — Descomposición LMP en energía/congestión + comparación contra bolsa real

Fecha: 2026-08-20. Sigue a `2026-08-18-lmp-nodal-market-design.md`, que ya
definía "precio único = componente de energía de los LMPs (lambda del bus de
referencia)" para el Escenario A. Esa definición nunca se implementó así: hoy
`status_quo.py` y el chart de precios usan el LMP crudo de una zona elegida por
posición en lista (`subarea_names[0]`), sin descomponer energía/congestión.
Este spec corrige eso y agrega la comparación contra el precio de bolsa real
que hoy solo existe para `level=ideal`.

## Objetivo

1. Calcular un **precio único (LMPE)** real: componente de energía del LMP,
   escalar por hora, igual para todo el sistema — no el LMP de una zona
   arbitraria.
2. Exponer la **congestión por zona (LMPC)** por separado, granular
   hora×zona, como insumo para un futuro mapa interpolado (fuera de alcance
   de este spec, pero el dato no debe agregarse prematuramente).
3. Comparar el precio único contra el **precio de bolsa real (`PrecBolsNaci`)**
   para corridas `level=lmp`, igual que ya existe para `level=ideal`.

## Hallazgo técnico (investigación previa)

EGRET separa LMP = LMPE + LMPC nativamente, pero **solo con la formulación
PTDF** (`create_ptdf_dcopf_model`), no con `btheta_power_flow` (la que usa hoy
`egret_engine.py:56` para el despacho por hora). `LMPE` es el dual de
`m.eq_p_balance`, una restricción **escalar** (no indexada por bus) en la
formulación PTDF (`egret/model_library/transmission/bus.py:265`,
`declare_eq_p_balance_ed`). No hace falta reimplementar el álgebra de PTDF:
basta leer ese dual del modelo resuelto.

## Approach

Cambiar el `solve_dcopf` por-hora en `egret_engine.py` de la formulación
btheta (implícita, default) a `create_ptdf_dcopf_model`, con
`return_model=True`. La etapa de compromiso (UC, binarias on/off,
`network_constraints='btheta_power_flow'`) no se toca — solo cambia la
resolución del despacho económico con compromiso fijo.

btheta y PTDF son formulaciones matemáticamente equivalentes del mismo flujo
DC lossless: mismo despacho óptimo, mismo costo total, solo cambia la
estructura de duales disponible. Se valida comparando `total_cost`/`dispatch`
antes/después contra la fixture dorada existente (`tests/fixtures/topology/`).

Alternativas descartadas:
- Promedio ponderado por demanda de LMPs de zona: no es LMPE real, mezcla
  congestión — el error que este spec corrige.
- Reimplementar PTDF/shift-factors propios: EGRET ya lo resuelve
  correctamente; reinventar es riesgo sin beneficio (YAGNI).

## Cambios por componente

**`app/nodal/engine/egret_engine.py`** — por cada hora, tras resolver con
`create_ptdf_dcopf_model` y `return_model=True`:
- `lmp_energy[t] = value(m.dual[m.eq_p_balance])` (escalar).
- `lmp_congestion[zone][t] = lmp[zone][t] - lmp_energy[t]` (resta simple sobre
  el LMP combinado que EGRET ya escribe en `md`).

**`app/nodal/engine/base.py`** (`NodalSolution`) — dos campos nuevos:
- `lmp_energy: list[float]` (24h).
- `lmp_congestion: dict[str, list[float]]` (por zona, sin agregar).

**`app/nodal/settlement/status_quo.py`** — bug de correctitud, no solo de
chart: `energy_price` pasa de `sol.lmp[sol.reference_zone][t]` a
`sol.lmp_energy[t]`. Afecta ingreso de generación, pago de carga y uplift del
Escenario A — no solo la visualización.

**`app/nodal/reporting.py`** — agrega series `lmp_energy` y `lmp_congestion`
al reporte/CSV nodal existente.

**`app/data/actuals.py`** (`load_reference_price`) — nueva rama:
`level == "lmp"` → `load_actual_bolsa` (mismo real que usa `ideal`; LMPE es la
magnitud comparable a un precio único nacional).

**`services/api/main.py`** — generaliza `_price_comparison_df` (hoy solo lee
`run.price_path`/columna `ideal_marginal_price`) para aceptar una serie modelo
genérica; para runs `lmp` usa `lmp_energy` en vez de `price_path`. Reutiliza el
formato `PricePoint` (`{datetime, model_mpo, xm_mpo}`) existente — sin schema
nuevo.

**Frontend:**
- `price-curves-chart.tsx`: "Precio único" deja de ser alias visual de
  `referenceZone` (`key === referenceZone ? t("nodal.singlePrice") : key`).
  Pasa a ser su propia serie (`lmp_energy`), siempre presente en el chart. La
  zona de referencia se muestra como zona normal, sin estilo especial —
  perdió todo significado económico distintivo.
- Nuevo componente de congestión por zona: reutiliza la estructura de
  `PriceCurvesChart` (líneas por zona/24h), alimentado por
  `lmp_congestion`.
- Comparación precio único vs bolsa real: reutiliza `PriceSeriesChart` tal
  cual (ya espera `{datetime, model_mpo, xm_mpo}`) — cero componente nuevo,
  solo wiring de datos hacia el endpoint de runs `lmp`.

## Testing

- Unitario: `egret_engine.py` — `lmp_energy[t]` igual para casos sin
  congestión (ninguna línea al límite); `lmp_congestion[zone][t] == 0` en ese
  caso; con congestión forzada (fixture con línea de capacidad reducida),
  `lmp[zone] == lmp_energy + lmp_congestion[zone]` exacto.
- Regresión: `total_cost` y `dispatch` de la fixture dorada nodal
  (`tests/fixtures/topology/`) sin cambios tras pasar de btheta a PTDF en el
  despacho por hora (mismo LP, misma solución).
- `status_quo.py`: settlement re-verificado a mano en el caso pequeño
  existente con el nuevo `energy_price`.
- `load_reference_price(level="lmp")`: reusa el test existente de la rama
  `ideal` con el level cambiado.
- Frontend: actualizar `price-curves-chart.test.tsx` (ya no depende de
  `referenceZone` para la serie "precio único"); test nuevo del componente de
  congestión.
- Gates: `uv run ruff check`, `uv run ruff format --check`, `uv run pytest -q`,
  `pnpm lint` / `pnpm test` (frontend).

## Fuera de alcance

- Mapa interpolado de congestión (el dato queda listo — granular por
  zona/hora — pero la visualización de mapa es trabajo futuro separado).
- Backfill de runs LMP existentes: son de prueba, se descartan (confirmado
  por el usuario).
- Pérdidas (DC-OPF sigue lossless; LMPE+LMPC es la descomposición completa
  sin término de pérdidas, consistente con el resto del módulo nodal).

## Riesgos

- Cambiar la formulación del despacho por-hora (btheta → PTDF) toca el motor
  para **todas** las corridas LMP, no solo el cálculo de precio. Mitigación:
  test de regresión de despacho/costo contra fixture dorada antes de mergear.
- `create_ptdf_dcopf_model` puede exponer opciones/comportamiento de PTDF
  (`ptdf_options`, sensibilidad numérica de line outages) distintas a btheta;
  revisar defaults de EGRET al implementar.
