# Heuristica de precios de oferta para fechas recientes — diseno

Fecha: 2026-08-11
Issue: [#30](https://github.com/jccamargo94/gridforge/issues/30)
Relacionado: [#35](https://github.com/jccamargo94/gridforge/issues/35) (test e2e
iterativo), [#36](https://github.com/jccamargo94/gridforge/issues/36) (precio por
configuracion en ciclo combinado, fuera de alcance v1)

## Contexto

`PrecOferDesp` (ofertas de precio por recurso, fuente de `ofertas.csv`) se publica
por **mes calendario completo, un mes despues**: verificado en vivo 2026-08-11 contra
`pydataxm.ReadDB.request_data("PrecOferDesp", "Recurso", ...)`, datos presentes hasta
2026-07-30, vacios desde 2026-08-01. `case_builder.py:108-114` ya detecta este hueco y
lanza `ValueError` explicito — pero eso bloquea correr dispatch para fechas recientes
por completo.

Este documento disena una heuristica que estima `ofertas.csv` para esas fechas,
sustituyendo el `raise` por un fallback automatico.

**Fuera de alcance, deliberadamente**:
- El ciclo de validacion/calibracion completo (comparar el estimado contra el
  dispatch real una vez XM publique el dato definitivo) — bloqueado por
  [#34](https://github.com/jccamargo94/gridforge/issues/34) (schema mismatch
  `dCondIniP`/`dCondIniU` bloquea correr con datos reales). Se deja para un spec
  futuro una vez esa plomeria este resuelta.
- Heuristica estacional/historica para recursos que nunca marginan en el periodo
  sin publicar.
- Caso especial de precio-por-configuracion en plantas de ciclo combinado (CC) — ver
  [#36](https://github.com/jccamargo94/gridforge/issues/36).
- El bug de cacheo en `ensure_ofertas`/`ensure_dispo_declarada` (`app/data/xm_bulk.py`):
  una vez `ofertas_{year}.csv` existe, nunca se vuelve a chequear contra XM aunque se
  publiquen meses nuevos. Riesgo relacionado, no se arregla en este spec.

## 1. Que datos estan realmente frescos (verificado en vivo, no asumido)

| Dataset | Mecanismo | Rezago real (verificado 2026-08-11) |
|---|---|---|
| `PrecOferDesp` (precio de oferta, `ofertas.csv`) | `pydataxm` bulk | 1 mes calendario completo — **el hueco a llenar** |
| `DispoDeclarada` (disponibilidad/Pmax, `dispo_declarada.csv`) | `pydataxm` bulk | Fresco hasta hoy (`request_data` devolvio filas hasta 2026-08-11) |
| `PrId` (predespacho ideal, generacion despachada por recurso/hora) | Blob por fecha (`ensure_data_for_date`) | Fresco hasta hoy (descarga real confirmada para 2026-08-04, 07, 10, 11) |
| `iMAR` (costo marginal / MPO nacional por hora) | Blob por fecha | Fresco **dia adelante** (confirmado: archivo de 2026-08-12 disponible el 2026-08-11) — **pero el codigo actual nunca lo descarga con exito, ver 1.1** |
| OFEI (`prices`/`cc_price` — precio declarado, plano o por configuracion CC) | Blob por fecha | Mismo rezago de mes calendario que `PrecOferDesp`: el archivo de hoy (agosto, mes en curso) no trae ninguna linea de precio, pero el de un mes ya cerrado si — verificado en vivo contra `data/2026-07-07/OFEI0707.txt`: 75 lineas de precio plano (`CHIVOR , P, 151000`) y lineas por configuracion en plantas CC (`FLORES4CC , P1, 1368810` .. `P4`). El parser (`app/data/ofei.py`) funciona correctamente contra el formato real — no es codigo muerto ni un formato viejo/deprecado ([#36](https://github.com/jccamargo94/gridforge/issues/36) actualizado con este hallazgo. |

Es decir: no existe un campo "precio de oferta por recurso" fresco (mes en curso) en
ninguna fuente — todas comparten el mismo rezago de mes calendario. `PrId`/`iMAR`
(generacion y MPO) son las unicas fuentes frescas, y de ahi sale la heuristica.
Si existe generacion despachada por recurso (`PrId`) y costo marginal del sistema por
hora (`iMAR`) frescos — de ahi sale la heuristica: inferir que recurso marca cada hora
y, si su oferta es plana durante el dia, su precio de oferta = el MPO de la hora en que
marca.

### 1.1 Bug bloqueante: `iMAR` nunca se descarga

`app/data/download.py` y `app/data/paths.py` agregan el sufijo `_NAL` tanto a `PrId`
como a `iMAR`:

```python
complement = "_NAL" if file_type in {"PrId", "iMAR"} else ""
```

Verificado en vivo: el archivo real es `iMAR{MMDD}.txt` (sin `_NAL`) — solo `PrId`
lleva el sufijo. Con el sufijo incorrecto, XM responde
`{"nombreExcepcion":"ExcepcionSinDatos", ...}` para toda fecha de 2026 probada. Este es
el prerequisito de todo lo demas: sin este fix, no hay MPO fresco disponible.

Fix: quitar `"iMAR"` del set que agrega `_NAL`, en ambos archivos.

### 1.2 Unidades del MPO (verificado, no de memoria)

`iMAR` trae tres filas por dia: `"Costo Marginal"`, `"Delta"`, `"MPO"` (24 valores
horarios cada una). Valores tipicos observados: ~990,000–1,054,000. Comparado contra el
orden de magnitud real de precio de bolsa en Colombia (cientos de COP/kWh, ver memoria
`xm-data-source-matrix` — `PrecBolsNaci` en COP/kWh, escalado `*1e3` en
`loaders.py:46` para llegar a COP/MWh), estos valores de `iMAR` **ya estan en
COP/MWh**, no COP/kWh.

`ofertas.csv`'s columna `Value`, en cambio, sigue la convencion COP/kWh cruda —
`case_builder.py` hace `ofertas.Value * 1e3` para construir `beta` en COP/MWh
(`case_builder.py:336-341`). Por lo tanto la heuristica debe escribir
`Value = mpo_hora_ganadora / 1e3` para no romper esa escala aguas abajo. Este es
exactamente el tipo de bug de escala que ya ocurrio una vez en este repo (revenue BESS
inflado 1000x, Fase 1) — se deja explicito aqui en vez de asumir.

Segunda conversion, independiente de la anterior: `dispo_declarada.csv` (Pmax) esta en
**kW** (`case_builder.py` hace `dispo["dispo"] * 1e-3` bajo el comentario
`# Valores en MWh`), mientras que `PrId` (generacion despachada) esta en **MW crudo,
sin escalar** (`case_builder.py` usa `demand_pronos` directo desde `PrId` sin ningun
factor — confirmado tambien por el comentario de `agc.py`: *"Values are MW in the raw
blob"*). La regla "a media maquina" (`0 < despachado < disponible`) compara ambos
directamente, asi que `dispo_declarada` debe convertirse a MW (`*1e-3`) antes de
comparar contra `PrId` — si no, `disponible` queda ~1000x mas grande que
`despachado` siempre, la regla nunca filtra nada, y la heuristica degrada
silenciosamente a "todo cae al fallback de ultimo precio" sin que ningun test con
datos autoconsistentes lo note.

## 2. Arquitectura

Paquete nuevo `app/data/heuristic/` (no un solo archivo — deja espacio para que
`#36` y futuras heuristicas relacionadas vivan ahi sin reabrir la estructura):

```
app/data/heuristic/
  __init__.py
  biddings.py       # estimate_ofertas() y el algoritmo de deteccion/asignacion
```

`biddings.py` expone una funcion pura, sin red ni storage:

```python
def estimate_ofertas(
    dispatch_date: date,
    dispo_declarada: pd.DataFrame,   # ya filtrado a dispatch_date
    predespacho: pd.DataFrame,        # PrId parseado: generacion por recurso/hora
    mpo_horario: pd.Series,           # iMAR fila "MPO", 24 valores indexados 0-23
    oferta_full: pd.DataFrame,        # historial completo (ya cargado por case_builder)
) -> pd.DataFrame:  # columnas: Date, resource_name, Value, is_estimated=True
```

Unico call site nuevo, en `case_builder.py` (reemplaza el `raise` actual en
`ofertas.empty`, `case_builder.py:108-114`): si `PrId` e `iMAR` estan disponibles para
`DISPATCH_DATE`, llama `estimate_ofertas(...)` y continua con el resultado; si tampoco
esos estan disponibles, `raise ValueError` (mensaje actualizado, sin referenciar la
heuristica como si ya hubiera fallado por otra razon).

## 3. Algoritmo de deteccion y asignacion

### 3.1 Candidatos por hora

Por cada hora `h` y recurso `r`: `r` es **candidato a marginar en `h`** si
`0 < predespacho[r, h] < dispo_declarada[r, h]` — generando, pero no al tope de lo
disponible esa hora ("a media maquina"). v1 aplica esta misma regla a todos los
recursos, sin caso especial de configuraciones CC ([#36](https://github.com/jccamargo94/gridforge/issues/36)).

### 3.2 Resolucion por eliminacion

Construir la matriz hora x recurso de candidatos. Iterar:

1. Buscar una hora `h` con **exactamente un** candidato `r` restante.
2. Si existe: `r` queda **resuelto** — su precio estimado = `mpo_horario[h] / 1e3`.
   Remover `r` de la lista de candidatos de **todas las demas horas** (ya se le asigno
   precio; no hace falta que siga compitiendo en otras horas).
3. Repetir hasta que no quede ninguna hora con exactamente un candidato sin resolver.

Recursos que nunca llegan a ser el unico candidato de ninguna hora quedan
**sin resolver** por este metodo (paso 3.3). Este es el criterio que pediste: una hora
donde el recurso es el unico candidato es evidencia confiable de su MPO real; una hora
con multiples candidatos no lo es y se descarta para todos los candidatos de esa hora
(no solo para uno) hasta que la eliminacion la deje sin ambiguedad o hasta que el
proceso termine.

Nota: por construccion, un recurso resuelto solo puede tener **un** precio asignado
(nunca hay conflicto de "dos valores distintos para el mismo recurso") — la eliminacion
ya lo garantiza, a diferencia de un enfoque de promedio/desviacion estandar sobre todas
sus horas candidatas (que si podia mezclar horas donde el recurso no marginaba en
realidad).

### 3.3 Fallback para recursos sin resolver

`Value` = ultimo precio publicado para ese recurso en `oferta_full`, tomando la fila
con el `Date` mas reciente (ordenar por `Date` antes de tomar la fila — corrige el bug
existente en `case_builder.py:278-282`, que usa `.head(1)` sobre un frame sin ordenar
y por lo tanto no garantiza tomar el dato mas reciente).

Nota: para plantas CC, `oferta_full`/`PrecOferDesp` no distingue configuracion (una
sola `Value` por recurso), aunque OFEI si tiene precio por configuracion en meses
cerrados (`P1`..`P4`, ver seccion 1). Usar esa granularidad queda para
[#36](https://github.com/jccamargo94/gridforge/issues/36) — v1 usa la misma `Value`
plana para CC que para el resto.

## 4. Trazabilidad

El DataFrame que retorna `estimate_ofertas` incluye `is_estimated: bool` (siempre
`True` en este flujo). No se persiste dentro de `ofertas/ofertas_{year}.csv` (el
archivo real de `pydataxm`) — se guarda aparte, en
`ofertas_estimado/ofertas_estimado_{year}.csv`, mismo patron de storage que los demas
loaders (`app/storage`, no `open()` plano). Mantiene el archivo real limpio y deja lista
la comparacion real-vs-estimado del ciclo de calibracion futuro (fuera de alcance, ver
Contexto) sin mezclar fuentes en un mismo archivo.

`case_builder.py` no necesita tratar las filas estimadas distinto de las reales para
construir el modelo — `is_estimated` es solo para reporting/evaluacion futura.

## 5. Testing

Fixture nuevo (mismo patron que `tests/fixtures/xm_smoke/`) con `PrId`, `iMAR` y
`dispo_declarada` sinteticos para una fecha donde el resultado esperado es conocido:
al menos un recurso claramente "a media maquina" en una hora sin otros candidatos
(caso resuelto), un recurso con horas candidatas ambiguas (caso sin resolver, cae a
fallback), y un recurso ausente de toda hora candidata (fallback puro).

Test e2e: llama `estimate_ofertas` con esos fixtures y verifica: (a) el recurso
resuelto recibe `Value = mpo_hora / 1e3` de la hora correcta; (b) el recurso ambiguo
y el ausente reciben el ultimo precio publicado; (c) `is_estimated=True` en las tres
filas. No requiere red ni credenciales XM.

Este test es el punto de partida, no la cobertura final — casos borde adicionales se
agregan iterativamente, ver [#35](https://github.com/jccamargo94/gridforge/issues/35).

## 6. Riesgos conocidos, no resueltos aqui

- `ensure_ofertas`/`ensure_dispo_declarada` (`app/data/xm_bulk.py`) cachean por
  `if storage.exists(path): return` — un `ofertas_{year}.csv` creado en agosto nunca
  se vuelve a chequear en septiembre aunque XM ya haya publicado el mes. No afecta
  este spec directamente (la heuristica no depende de ese cache), pero significa que
  el "ultimo precio publicado" (seccion 3.3) puede quedar desactualizado si nadie
  fuerza un refetch — riesgo pre-existente, no introducido por este cambio.
- El ciclo de calibracion (comparar contra dispatch real) no se puede probar
  end-to-end hasta que [#34](https://github.com/jccamargo94/gridforge/issues/34) este
  resuelto.

## Adendum 2026-08-11 (issue [#36](https://github.com/jccamargo94/gridforge/issues/36)): decision -- CC se mantiene plana en la heuristica

Verificado contra datos reales: `PrId` de una fecha reciente (2026-08-02) lista las
plantas CC por planta completa (`"FLORES 4 CC"`), y `dispo_declarada` (fresca) igual.
La granularidad por configuracion solo existe en OFEI (`cc_dispo`/`cc_price`), que
comparte el rezago de mes calendario de PrecOferDesp y por tanto esta vacia
exactamente en las fechas que la heuristica debe estimar. Por eso v1 (y el plan de
[#30](https://github.com/jccamargo94/gridforge/issues/30)) dejan CC como recurso plano
de planta completa: el candidato "a media maquina" se detecta a nivel de planta y su
`Value` = MPO de la hora resuelta / 1e3, igual que el resto. El split por configuracion
sigue siendo el camino de los meses cerrados, via `cc_price`/`cc_dispo` en
`case_builder.py`. #36 se cierra con esta decision: no se implementa estimacion por
configuracion en la heuristica.
