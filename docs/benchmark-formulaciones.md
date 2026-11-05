---
title: "Benchmark de formulaciones"
layout: default
---

# Benchmark de formulaciones: tiempo mínimo en línea

El modelo impone el tiempo mínimo en línea (min-up) con una desigualdad
**agregada** por ventana: `sum(z[t..t+TMG-1]) >= TMG * zup[t]`. Una alternativa
clásica (Rajan–Takriti / Malkin) es la forma **desagregada**:
`z[t'] >= zup[t]` para cada `t'` de la ventana. Ambas son equivalentes en puntos
enteros; la desagregada tiene una relajación LP más ajustada pero más filas.

La opción vive en `UnitCommitmentModel(case, min_up_formulation=...)`
(`aggregated` por defecto; **el default no cambió**). El harness es
`app/benchmarks/formulations.py` y usa solo instancias sintéticas (24 períodos,
HiGHS, `mip_rel_gap=1e-4`, límite 60 s):

```bash
uv run python -m app.benchmarks.formulations --sizes 10 20 40 --seeds 0 1
```

| gens | formulación | filas | tiempo (s) | objetivo | estado |
|---|---|---|---|---|---|
| 10 | aggregated | 2167 | 0.94 | 1,452,265 | optimal |
| 10 | disaggregated | 2970 | 1.11 | 1,452,265 | optimal |
| 20 | aggregated | 4324 | 1.88 | 1,979,286 | optimal |
| 20 | disaggregated | 5727 | 1.98 | 1,979,252 | optimal |
| 40 | aggregated | 8618 | 8.47 | 3,482,905 | optimal |
| 40 | disaggregated | 11225 | 10.44 | 3,482,905 | optimal |

(Semilla 0; con tolerancia 1e-4 los objetivos pueden diferir ligeramente.)

**Conclusión honesta:** en estas instancias sintéticas la formulación
desagregada **no mejora** el tiempo de solve con HiGHS (el presolve ya ajusta la
agregada) y agrega ~30 % de filas. No hay evidencia para cambiar el default. El
resultado puede variar con flotas más grandes o con datos reales de XM, que este
benchmark no usa. Las rampas no se compararon (la formulación actual es una
desigualdad lineal simple sin variante alternativa obvia).
