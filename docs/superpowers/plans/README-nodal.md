# Módulo nodal LMP (liquidación por precios locales)

README del módulo nodal de gridforge: despacho nodal basado en EGRET y
comparación de dos regímenes de liquidación (escenario *status_quo* nacional
vs. liquidación LMP por nodo/barra).

## Qué hace el módulo

Para una fecha dada, el módulo nodal construye una red nodal (zonal, en v1)
a partir de un archivo `NodalNetwork` JSON y la demanda nacional XM de esa
fecha, resuelve un despacho con el motor **EGRET** (`app/nodal/engine/egret_engine.py`),
y sobre ese mismo despacho calcula **dos liquidaciones**:

- **Escenario A — `status_quo`** (`app/nodal/settlement/status_quo.py`):
  régimen actual simplificado de precio único nacional. Toda la energía se
  paga al LMP de la **zona de referencia** (`reference_zone`, en la red de
  ejemplo `norte`). La renta de congestión horaria (pago total de demanda a
  LMP menos ingreso total de generación a LMP) se recauda de la demanda como
  un *uplift* distribuido **proporcional a la participación de carga** de
  cada zona (`uplift_share = congestion_rent * load_zone / load_total`).
- **Escenario B — `lmp`** (`app/nodal/settlement/lmp.py`): liquidación
  ex-ante por barra. Cada zona paga su **LMP propio** por la energía que
  consume y cada generador cobra el LMP de la zona en que está por lo que
  despacha. La renta de congestión queda embebida en los precios (pagos a
  LMP); **no hay componente de pérdidas** en v1.

La comparación (`app/nodal/settlement/compare.py`) produce métricas agregadas
(delta de pagos de demanda y de ingresos de generación entre A y B, precio
promedio y volatilidad por zona, renta de congestión total) y la **matriz de
redistribución**: cuánto cambia el pago de cada zona de carga al pasar del
régimen nacional al LMP por barra.

## Supuestos de simplificación (v1)

- **Un solo despacho, dos liquidaciones.** Se resuelve una vez el problema
  nodal (compromiso unitario con restricciones de red vía EGRET, y luego un
  DC OPF por hora con el compromiso fijado para extraer LMPs, despacho y
  flujos). Ambos escenarios de liquidación se calculan *a posteriori* sobre
  ese mismo despacho — **no hay re-optimización por régimen**.
- **Sin make-whole.** Ningún generador recibe pagos mínimos de rentabilidad
  si su ingreso a LMP no cubre sus costos.
- **Sin pérdidas.** El LMP es un solo valor por barra (energía + congestión);
  no hay componente de pérdidas marginales.
- **Sin reservas** ni productos ancillares; solo energía.
- LMPs **ex-ante** (del problema de despacho), sin re-despacho posterior.
- El precio de corto plazo de la zona de referencia en el escenario A es el
  LMP del despacho nodal, no una serie externa de bolsa.

## Uso CLI

```bash
uv run python -m app run <fecha> -t lmp --nodal-network <path-to-network-json>
```

- `-t lmp` enruta la corrida al runner nodal (`app/nodal/runner.py`).
- `--nodal-network <archivo>` usa ese JSON `NodalNetwork`. **Si se omite**,
  se usa la red empaquetada `app/nodal/data/example_zonal_network.json`
  (`load_network` en `app/nodal/runner.py`).
- El `solver` default es `cbc`, igual que el resto del repo.
- Directorio de salida: `{out}/{fecha}-lmp/`, con `out` default
  `data/results` (p. ej. `data/results/2024-04-18-lmp/`).

## Artefactos de salida

Escritos por `app/nodal/reporting.py` en el directorio `{fecha}-lmp/`:

| Archivo | Contenido |
|---|---|
| `lmp.csv` | `timestamp, bus, lmp` — LMP por hora y zona. |
| `dispatch.csv` | `generator, zone, fuel, hour, dispatch_mw` — despacho por generador. |
| `branch_flows.csv` | `timestamp, branch, flow_mw` — flujo por rama. |
| `settlement_status_quo.csv` | `zone, hour, load_payment, gen_revenue, uplift` — liquidación escenario A. |
| `settlement_lmp.csv` | `zone, hour, load_payment, gen_revenue` — liquidación escenario B. |
| `comparison.csv` | Matriz de redistribución: `zone, load_payment_a, load_payment_b, delta`. |
| `summary.json` | Métricas de comparación (deltas de pagos/ingresos, `price_avg_<z>`, `price_vol_<z>`, renta de congestión total), totales y conteos (`generator_count`, `branch_count`). |

## Red de ejemplo empaquetada

`app/nodal/data/example_zonal_network.json` es una **plantilla de 3 zonas
claramente rotulada** (`norte` / `centro` / `sur`) con `name:
"example_zonal_network"`, dos ramas (`NC`, `CS`) y tres generadores
(`G_N` hidro barato, `G_C` gas, `G_S` carbón). Su campo `demand_shares`
(`norte: 0.4`, `centro: 0.35`, `sur: 0.25`) **suma 1.0**, lo que permite que
`build_zonal_loads` reparta la demanda nacional XM horaria de *cualquier*
fecha entre las zonas (`load_zone[h] = demanda_nacional[h] * share_zone`).
Por eso corre contra cualquier fecha que tenga demanda XM nacional; no
depende de topología real.

## Pendiente / diferido a fases posteriores

- **Loader de topología real XM** (líneas de transmisión + mapeo
  generador-a-zona desde datos públicos de XM, versionado con checksum):
  los módulos `network/loaders.py` y `network/transform.py` del spec.
  `build_zonal_loads` ya soporta el patrón `demand_shares` que ese loader
  real alimentará.
- **Motor `PrescientNodalEngine`** (fase 4 del spec) implementando el mismo
  protocolo `NodalEngine`: agrega make-whole, reservas, pérdidas y modelado
  de error de pronóstico.
- **Fase 2** — endpoints FastAPI + worker + persistencia en DB
  (`runs` / `metric_sets`) para corridas nodales.
- **Fase 3** — frontend (mapa zonal, curvas de precio, matriz de
  redistribución).
- **Calibración vs. precio real de bolsa** (escenario A como ancla) con
  RMSE/MAE, sobre fechas reales una vez que `data/` esté poblado.