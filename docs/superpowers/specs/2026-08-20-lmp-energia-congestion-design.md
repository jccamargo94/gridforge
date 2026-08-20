# Spec — Precio promedio ponderado + congestión por zona + comparación contra bolsa real

Fecha: 2026-08-20 (revisado el mismo día — ver "Corrección" abajo). Sigue a
`2026-08-18-lmp-nodal-market-design.md`, que definía "precio único = lambda
del bus de referencia" para el Escenario A. Ese enfoque, y el intento inicial
de arreglarlo con la descomposición LMPE/LMPC de EGRET, resultaron ambos
inválidos (ver Corrección). Este spec reemplaza la idea de "precio único" por
un **precio promedio ponderado por demanda**, calculable directo de los datos
que el motor ya produce, sin tocar EGRET.

## Objetivo

1. Calcular un **precio promedio ponderado por demanda**: `Σ(LMP_zona ×
   carga_zona) / Σ(carga_zona)` por hora — la cantidad de energía transada
   (consumida) en cada zona pondera su LMP. Reemplaza cualquier noción de
   "precio único" basada en una zona arbitraria.
2. Exponer la **congestión por zona** por separado, granular hora×zona
   (`LMP_zona − precio_promedio`), como insumo para un futuro mapa
   interpolado (fuera de alcance de este spec).
3. Comparar el precio promedio ponderado contra el **precio de bolsa real
   (`PrecBolsNaci`)** para corridas `level=lmp`, igual que ya existe para
   `level=ideal`.

## Corrección (por qué esto no es el spec original)

El spec original proponía usar la descomposición nativa de EGRET
(`LMP = LMPE + LMPC`, disponible solo con la formulación PTDF) para obtener
un "precio único" reference-independent. Se verificó **antes de implementar**
que esto es falso:

- `egret/data/ptdf_utils.py:576`: `return self._insert_reference_bus(LMP,
  LMPE)` — el LMP del bus de referencia se **define** como `LMPE`, por
  construcción del algoritmo (el bus de referencia queda fuera del vector
  `buses_keys_no_ref` sobre el que se calcula la congestión), no porque ese
  bus esté económicamente libre de congestión.
- btheta y PTDF son formulaciones equivalentes del mismo despacho (mismo LMP
  físico por bus — ya verificado como parte de la Task 1 original). Si
  `LMP[ref] := LMPE` por construcción, y el LMP físico de cada bus no cambia
  entre formulaciones, entonces `LMPE == λ_zona_referencia` — exactamente la
  misma cantidad arbitraria que el bug original, con más código encima.
- **Verificación empírica** (motor actual, sin modificar, variando
  `reference_zone` en la fixture de 3 zonas congestionada):
  ```
  reference_zone=norte  -> lmp[norte]=20.0  lmp[centro]=80.0  lmp[ref]=20.0
  reference_zone=centro -> lmp[norte]=20.0  lmp[centro]=80.0  lmp[ref]=80.0
  ```
  Los LMPs físicos por zona (20/80) no cambian según qué zona sea la
  referencia — solo cambia cuál de esos valores queda expuesto como
  `lmp[reference_zone]`. Confirma que la vía PTDF no resuelve nada.

**Consecuencia:** no hace falta tocar el motor EGRET en absoluto. El precio
promedio ponderado por demanda se calcula con datos que `NodalSolution` ya
expone (`lmp`, `loads`), como post-procesamiento puro. Esto elimina el riesgo
de regresión de despacho que el spec original aceptaba (cambio de formulación
btheta→PTDF).

**Por qué el promedio ponderado por demanda es la magnitud correcta:** bajo
ponderación por carga, las desviaciones de congestión suman cero exactamente
— `Σ carga_zona × (LMP_zona − precio_promedio) = Σ carga_zona×LMP_zona −
precio_promedio × Σcarga_zona = 0` por construcción algebraica. Esto es
consistente con la intuición ya presente en `congestion_rent()`
(`app/nodal/settlement/rent.py`): la congestión es una redistribución, no un
costo neto del sistema. Es también la definición estándar de "precio
promedio del sistema" en mercados reales (promedio ponderado por la demanda
que efectivamente paga cada precio nodal).

## Approach

Nueva función pura en `app/nodal/engine/pricing.py`, llamada al final de
`EgretNodalEngine.solve()` (después de tener `lmp` y `loads` completos, antes
de construir `NodalSolution`):

```python
def demand_weighted_average_price(
    lmp: dict[str, list[float]], loads: dict[str, list[float]],
    buses: list[str], n_hours: int,
) -> list[float]:
    return [
        sum(lmp[b][t] * loads[b][t] for b in buses) / sum(loads[b][t] for b in buses)
        for t in range(n_hours)
    ]


def congestion_component(
    lmp: dict[str, list[float]], avg_price: list[float],
    buses: list[str], n_hours: int,
) -> dict[str, list[float]]:
    return {b: [lmp[b][t] - avg_price[t] for t in range(n_hours)] for b in buses}
```

`NodalSolution` gana dos campos: `lmp_avg: list[float]` (precio promedio
ponderado, 24h) y `lmp_congestion: dict[str, list[float]]` (por zona, sin
agregar). El motor EGRET, la formulación de despacho (btheta,
`network_constraints='btheta_power_flow'`), y todos los valores de
`dispatch`/`branch_flows`/`total_cost`/`lmp` quedan exactamente igual que
hoy — cero riesgo de regresión de despacho.

## Cambios por componente

**`app/nodal/engine/pricing.py`** (nuevo) — las dos funciones puras de
arriba.

**`app/nodal/engine/egret_engine.py`** — al final de `solve()`, antes de
`return NodalSolution(...)`:
```python
lmp_avg = demand_weighted_average_price(lmp, loads, [z.name for z in net.zones], len(time_keys))
lmp_congestion = congestion_component(lmp, lmp_avg, [z.name for z in net.zones], len(time_keys))
```

**`app/nodal/engine/base.py`** (`NodalSolution`) — dos campos nuevos:
`lmp_avg: list[float]`, `lmp_congestion: dict[str, list[float]]`.

**`app/nodal/settlement/status_quo.py`** — bug de correctitud, no solo de
chart: `energy_price` pasa de `sol.lmp[sol.reference_zone][t]` a
`sol.lmp_avg[t]`. Afecta ingreso de generación, pago de carga y uplift del
Escenario A.

**`app/nodal/reporting.py`** — agrega columnas `lmp_avg` y `lmp_congestion`
al `lmp.csv` existente (mismo artifact, mismo `lmp_path`, sin CSV nuevo ni
columna de DB nueva).

**`app/data/actuals.py`** (`load_reference_price`) — nueva rama:
`level == "lmp"` → `load_actual_bolsa` (mismo real que usa `ideal`).

**`services/api/main.py`** — nueva `_nodal_price_comparison_df` (análoga a
`_price_comparison_df` pero leyendo `lmp_avg` del artifact `lmp.csv` en vez
de `run.price_path`/`ideal_marginal_price`), expuesta en
`GET /runs/{id}` como `nodal.price_series`, mismo formato `PricePoint`
(`{datetime, model_mpo, xm_mpo}`).

**Frontend:**
- `price-curves-chart.tsx`: la línea "Precio promedio" deja de ser alias de
  `referenceZone` — pasa a ser su propia serie (`lmp_avg`), siempre presente.
- Nuevo componente de congestión por zona (`lmp_congestion`), separado, sin
  agregación (listo para un futuro mapa).
- Comparación precio promedio vs bolsa real: reutiliza `PriceSeriesChart`
  (ya espera `{datetime, model_mpo, xm_mpo}`).
- Copy/i18n: "Precio único" se reemplaza por "Precio promedio ponderado" en
  todos los textos visibles (título, subtítulo, leyenda).

## Testing

- Unitario `pricing.py`: caso sin congestión (todos los LMP iguales) →
  `lmp_avg[t] == LMP` constante, `lmp_congestion[zona][t] == 0` para toda
  zona. Caso congestionado (fixture de 3 zonas, cargas iguales 100 MW/zona,
  LMP 20/80/80) → `lmp_avg[0] == 60.0` (promedio simple porque las cargas son
  iguales), `lmp_congestion["norte"][0] == -40.0`,
  `lmp_congestion["centro"][0] == lmp_congestion["sur"][0] == 20.0`,
  identidad `Σ carga_zona × lmp_congestion[zona][t] == 0`.
- Regresión: `dispatch`/`branch_flows`/`total_cost`/`lmp` de la fixture
  existente **sin cambios** — el motor no se toca, solo se agrega
  post-procesamiento puro tras `solve()`.
- `status_quo.py`: settlement re-verificado con el nuevo `energy_price`
  (ahora `lmp_avg`), usando una variante de la fixture con
  `reference_zone="centro"` para probar que el resultado no depende de qué
  zona sea la referencia (el bug original sí dependía).
- `load_reference_price(level="lmp")`: reusa el patrón de test de la rama
  `ideal`.
- Frontend: actualizar tests de `price-curves-chart` (ya no depende de
  `referenceZone`); test nuevo del componente de congestión.
- Gates: `uv run ruff check`, `uv run ruff format --check`, `uv run pytest -q`,
  `pnpm lint` / `pnpm test` (frontend).

## Fuera de alcance

- Mapa interpolado de congestión (el dato queda listo — granular por
  zona/hora — pero la visualización de mapa es trabajo futuro separado).
- Backfill de runs LMP existentes: son de prueba, se descartan (confirmado
  por el usuario).
- Pérdidas (DC-OPF sigue lossless).
- Cualquier cambio a la formulación de despacho del motor EGRET (btheta se
  mantiene sin cambios).

## Riesgos

- Ninguno de despacho/motor — no se toca EGRET. El único riesgo es de
  correctitud del post-procesamiento (cubierto por los tests de identidad
  arriba: `Σ carga×congestión == 0`, `lmp_avg + congestión == lmp` por bus).
