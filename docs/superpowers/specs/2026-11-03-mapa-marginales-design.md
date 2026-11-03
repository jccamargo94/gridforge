# Mapa historico de recursos marginales (issue #86) - Diseno

Rama: `fase9c-recursos-marginales`. Fecha: 2026-11-03.

## Que resuelve
Inteligencia de mercado: que tecnologia (y zona) ha sido candidata a fijar el
precio de bolsa, por hora, a lo largo de un rango historico, con datos
observados (precio de bolsa + ofertas + disponibilidad). Sin Pyomo ni LMP.

## Desviacion deliberada del issue
El issue propone reutilizar `detect_marginal_resources`
(`app/data/heuristic/biddings.py`). No se reutiliza: esa funcion necesita PrId
(MW despachados) e iMAR por fecha, archivos que se descargan dia a dia y no
forman parte de los year CSVs; ademas resuelve una hora por recurso por
eliminacion, por lo que no produce una frecuencia por hora sobre un historico
largo. Aqui se usa un metodo por coincidencia de precio sobre los year CSVs
que el producto ya ingiere. Son enfoques complementarios, no equivalentes.

## Metodo (`app/market/marginal.py`)
Un recurso es candidato en la hora h si `dispo > 0` y su oferta del dia esta a
distancia relativa <= `tol` (default 2%) del precio de bolsa de esa hora. Con k
candidatos, cada uno pesa 1/k. Una celda (tecnologia, zona, hora) es la suma de
pesos dividida por las horas observadas con precio: fraccion esperada de dias
en que esa tecnologia/zona fijo el precio. Horas sin candidato = no atribuidas.
Unidades: oferta COP/kWh x1e3, `load_precio_bolsa` ya escala x1e3 -> COP/MWh.

## Zona
`resource -> zone` sale de la red PARATEC cacheada (`topology/network.json`,
escrita por `POST /topology/scrape`), con match por nombre normalizado exacto
(sin fuzzy, para no asignar zonas equivocadas). Si no hay red, solo vista por
tecnologia; la API informa `zone_mapped_share`.

## Privacidad
Solo se devuelven tecnologia y zona, nunca nombres de recurso (misma politica
que `app/market/merit.py`).

## API / UI
`GET /market/marginal-map?start=&end=&tol=` (rango 1..366 dias, `tol` 0..0.2).
Pagina `/marginal`: heatmap hora x tecnologia o zona.

## Limites conocidos
- Precio de bolsa = MPO + termino adicional: `tol` debe absorberlo; con `tol`
  chico quedan horas sin atribuir, con `tol` grande aumentan las ambiguas.
- Recursos sin oferta ese dia nunca se atribuyen.
- No se persiste el resultado (el calculo vectorizado de un ano es barato);
  persistir queda para cuando haga falta precalcular.
- Sin validar contra datos reales de XM: solo fixture sintetico y datos armados.
- Dias recientes: `PrecOferDesp` tiene ~1 mes de rezago, el rango debe estar
  dentro del periodo con ofertas publicadas.
