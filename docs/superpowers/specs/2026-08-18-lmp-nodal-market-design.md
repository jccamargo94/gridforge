# Spec — Módulo nodal LMP: comparación precio único vs. LMP ex-ante (caso colombiano)

Fecha: 2026-08-18. Sigue a la discusión de modernización del mercado
colombiano (paso de precio único ex-post a precios LMP ex-ante vinculantes) y
al interés de demostrar, con la plataforma GridForge, el diferencial económico
de ambos regímenes sobre el mismo sistema.

## Objetivo

Agregar a GridForge un **módulo nodal de mercados** que, sobre una
representación de la red eléctrica colombiana construida con topología pública
de XM, resuelva el despacho de mínimo costo y liquide el mismo resultado bajo
dos regímenes de precios:

- **Escenario A (status quo):** precio único nacional + congestión recuperada
  aparte de la carga (como hoy con los cargos por restricciones).
- **Escenario B (modernización):** LMP por bus, ex-ante y vinculante, con
  descomposición energía + congestión.

La entrega es una comparación cuantificable ("mismo sistema, dos regímenes, la
diferencia en $") consumible primero por CLI, luego por API/worker y
finalmente por el frontend.

El módulo se construye **dentro del repo GridForge** como un paquete aislado
(`app/nodal/`), siguiendo la visión de GridForge como plataforma que crece por
módulos sin acoplarse.

## Decisiones de diseño (acordadas en brainstorming)

1. **Ubicación:** todo el trabajo vive en `/home/user/projects/udea/gridforge`.
   El repo `personal/egret` queda como POC de referencia de EGRET/Prescient.
2. **Integración:** módulo aislado `app/nodal/` dentro de GridForge. El modelo
   de nodo único actual (`app/model/`) no se toca; queda como ancla de
   calibración del Escenario A.
3. **Red:** híbrida. El pipeline de carga/transformación de la red se escribe
   para la **red completa** desde el inicio; la primera salida usa la
   **agregación zonal** (~15-30 nodos). Migrar a red detallada es un cambio de
   parámetro de agregación, no de código.
4. **Topología:** se descarga de XM (líneas de transmisión, generadores con su
   agregación por zona/subzona). Demanda **zonal** directa de XM. Partición de
   zonas **según la estructura que publica XM**.
5. **Motor:** EGRET primero (DCOPF/SCUC + LP de pricing) para el núcleo LMP;
   Prescient como fase posterior (simulación DA/RT con reservas, uplift y
   liquidación completa). Separados por una abstracción de motor.
6. **Metodología:** un solo despacho (el de mínimo costo sobre la red), dos
   liquidaciones calculadas después como capa de reporte. No se re-optimiza por
   régimen. Esto aísla el efecto del régimen de precios manteniendo la física
   constante.
7. **Entregable:** full stack como meta (CLI+artefactos → API/worker →
   frontend), implementado por fases.

## Arquitectura del módulo

```
app/nodal/
  network/              # Modelo de red nodal
    loaders.py          # carga topología XM (líneas, nodos, zonas/subzonas)
                        #   escrito para red COMPLETA; zonal es un paso de transformación
    transform.py        # agrega a zonal (v1) o deja completa (futuro)
    to_egret.py         # NodalNetwork -> ModelData EGRET (bus/branch/gen)
    schemas.py          # pydantic v2: NodalNetwork, Zone, Branch, Generator, NodalCase
  engine/               # Abstracción de motor — permite EGRET -> Prescient
    base.py             # protocolo NodalEngine: solve() -> NodalSolution
    egret_engine.py     # implementación EGRET (DCOPF/SCUC + LP de pricing) — fase 1
    prescient_engine.py # implementación Prescient (DA/RT + liquidaciones) — fase 2
  settlement/           # Doble régimen sobre la MISMA solución
    status_quo.py       # Escenario A: precio único + congestión socializada
    lmp.py              # Escenario B: LMP por bus ex-ante (energía + congestión)
    compare.py          # diferencial A vs B por zona/hora + métricas
  reporting/            # artefactos CSVs comparativos y resúmenes
  cli.py                # subcomando: python -m app run <fecha> -t lmp
```

**Reuso de la plataforma existente (intacta):**

- `app/data/` — carga de insumos XM (demanda, ofertas, disponibilidad).
- `app/schemas/` — nuevos modelos pydantic (`NodalCase`, `NodalSolution`,
  `LmpResult`, `NodalNetwork`).
- `app/storage/`, `app/db/` — persistencia de corridas y artefactos (fase 2).
- `app/model/` (nodo único) — **no se toca**; ancla de calibración del Escenario A.

**Flujo de datos:** insumos XM + topología → `NodalCase` → motor EGRET resuelve
(SCUC + LP de pricing) → `NodalSolution` (dispatch + precios nodales) → se
liquida A y B → comparación → artefactos.

**Punto de extensión clave:** el protocolo `NodalEngine.solve() -> NodalSolution`.
La fase 2 (Prescient) implementa el mismo protocolo; settlement, reporting y
frontend no saben qué motor corre.

## Modelo de red nodal y pipeline de datos

```
datos crudos XM (líneas, generadores, zonas)
  -> app/nodal/network/loaders.py     # normaliza a NodalNetwork
  -> app/nodal/network/transform.py   # agrega a zonal (v1) o completa (futuro)
  -> app/nodal/network/to_egret.py    # NodalNetwork -> ModelData EGRET
```

**`NodalNetwork` (canónico, independiente del motor):**

- `zones/nodes`: zonas (v1) o buses completos (futuro), con demanda y
  generación agregada. La partición sigue la estructura zonal oficial de XM.
- `branches`: corredores entre zonas (v1) o líneas individuales (futuro), con
  reactancia y capacidad de transferencia (límite térmico).
- `generators`: cada generador con su zona asignada (agregación publicada por
  XM), capacidad, precio de oferta, rampas, min-up/down — reutilizando los
  datos ya cargados en `app/data/`.
- `load`: demanda por zona, directa de XM.
- **Versionado de topología:** cada `NodalNetwork` se guarda con fecha de
  vigencia y checksum (patrón `InputPack`). La red cambia en el tiempo (nuevas
  líneas, reconfiguraciones); cada corrida queda ligada a la red que usó.

## Motor EGRET (fase 1)

- Construir `ModelData` EGRET desde `NodalNetwork` (`to_egret.py`).
- Resolver unit commitment nodal / economic dispatch con **CBC** (solver
  disponible en el entorno; MIP para el UC, luego **LP de pricing** fijando los
  binarios para duales válidos — espejo del patrón fix-and-resolve de
  `app/model/model.py:324-345`).
- `NodalSolution` contiene: dispatch por generador/hora, LMPs por bus/hora
  (duales de los balances nodales), y los componentes de energía y congestión.

## Metodología de liquidación

**Un solo dispatch, dos liquidaciones.** El despacho físico (mínimo costo
sobre la red) es idéntico en ambos escenarios; la diferencia es la capa de
precios. No se re-optimiza por régimen.

**Escenario A — status quo (precio único + congestión socializada):**

- **Precio único** = componente de energía de los LMPs (el lambda del bus de
  referencia en teoría LMP), igual para todos los buses. Aproxima el precio de
  bolsa colombiano (costo marginal nacional ignorando congestión).
- Generadores cobran precio único × generación.
- Carga paga precio único × demanda + **cargo de congestión** (uplift): el
  costo total de congestión se recupera de la carga, como hoy con los cargos
  por restricciones.
- Señal de inversión: nula por ubicación.

**Escenario B — LMP ex-ante vinculante:**

- Cada bus paga/cobra su **LMP = energía + congestión** (sin pérdidas en v1;
  DCOPF sin pérdidas es el estándar limpio; con pérdidas se agrega después con
  `dcopf_losses`).
- Generadores cobran el LMP de su bus; la carga paga el LMP de su bus.
- Renta de congestión explícita y localizada: flujo × componente de congestión
  por rama.

**Comparación:**

| Métrica | qué muestra |
|---|---|
| Costo total de producción | igual en A y B (despacho idéntico) — prueba de aislamiento del régimen |
| Pago total de la demanda A vs B | ahorro/costo del cambio, en $ |
| Ingreso total de generación A vs B, por zona y tecnología | quién gana y quién pierde |
| Renta de congestión A vs B | de socializada a localizada |
| Precio promedio y volatilidad por zona (B) vs precio único (A) | señales locacionales de precio |
| Matriz de redistribución zona × Δpago | el "quién paga más/menos" para un regulador |

**Simplificaciones explícitas de v1** (documentadas): sin make-whole/uplift por
compromiso, sin pérdidas, sin mercados de reservas. Se agregan en refinamientos
posteriores; Prescient (fase 2) aporta liquidación completa con reservas,
uplift y dos etapas.

## Fases de implementación

**Fase 1 — CLI + artefactos (analítica):**

- Pipeline de red (loaders → transform zonal → `to_egret`) con fixture
  sintético zonal para tests offline (patrón `tests/fixtures/xm_smoke`; no
  asumir `data/`).
- Motor EGRET: SCUC + LP de pricing → `NodalSolution`.
- Settlement A/B + comparación + métricas.
- CLI: `run <fecha> -t lmp` → CSVs en `data/results/`.
- **Validación:** correr las fechas históricas ya validadas en GridForge
  (p. ej. 2024-04-18), calibrar el Escenario A contra el precio de bolsa real
  (el ancla), y presentar Escenario B como análisis contrafáctico.

**Fase 2 — API/worker:** persistir corridas LMP en DB (reusar `runs` /
`input_datasets`; agregar `nodal_results`), endpoints para lanzar/consultar/
descargar, worker ejecuta corridas largas.

**Fase 3 — Frontend:** dashboard de comparación — mapa zonal con LMPs, curvas
precio único vs. por zona, tabla de diferencial, matriz de redistribución
zona × Δpago.

**Fase 4 (post) — Prescient:** implementar `prescient_engine.py` tras el
protocolo `NodalEngine`; simulación DA/RT con reservas, uplift y liquidación
completa.

## Testing

- Unitarios: loaders, transform zonal↔completo, `to_egret`, settlement A/B
  (resultados verificables a mano en un caso pequeño), comparación, CLI.
- Fixture sintético zonal para pruebas offline sin datos XM.
- Golden test del pipeline nodal cuando haya datos reales.
- Calibración: Escenario A vs precio de bolsa real en fechas históricas;
  métricas RMSE/MAE como las existentes (`app/utils/metrics.py`).
- Gates: `uv run ruff check`, `uv run ruff format --check`, `uv run pytest -q`.
  Frontend (fase 3): `pnpm lint` / `pnpm test`.

## Fuera de alcance

- Red nodal detallada completa del SIN (el pipeline la soporta, pero la primera
  corrida usa la agregación zonal).
- Make-whole, uplift por compromiso, pérdidas y mercados de reservas (se agregan
  en refinamientos; Prescient los cubre en fase 2).
- Modelado del despacho como mercado de ofertas (el cambio de régimen se aísla
  al precio; un escenario de mercado ofertado queda como trabajo futuro).
- Derivados financieros / FTR.

## Riesgos

- La agregación zonal puede perder congestión intra-zona; mitigación: calibrar
  contra el precio de bolsa y documentar el nivel de agregación en cada corrida.
- La topología XM cambia de formato/disponibilidad; mitigación: copias locales
  con checksum y fecha de descarga (patrón `InputPack`).
- CBC puede ser lento en UC nodal con muchas zonas y binarias; mitigación:
  granularidad zonal en v1, timelimit/mipgap explícitos, y camino a solver
  comercial si se escala a red completa.