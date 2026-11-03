# Auditoria de oferta propia vs historico (issue #83) - Diseno

Rama: `fase9b-auditoria-oferta`. Fecha: 2026-11-03.

## Que resuelve
Chequeo de sanidad previo al envio de la oferta: "esta oferta es consistente
con lo que esta planta suele ofertar?". Es estadistica descriptiva sobre el
historico de la propia planta; **no recomienda un precio** (evita el problema
de poder de mercado de #79).

## Granularidad (diferencia con el texto del issue)
El issue pide banda "por planta/hora", pero `PrecOferDesp` en `ofertas.csv` es
**un precio por recurso por dia** (`refresh_ofertas` solo conserva
`Values_Hour01`). La banda es por planta y, cuando hay muestras suficientes,
por dia de la semana. No existe oferta horaria en este dataset.

## Calculo (`app/market/offer_audit.py`)
- Unidades: `Value` COP/kWh -> COP/MWh (x1e3, igual que `case_builder.py`).
- Ventana: los `window_days` dias previos a la fecha (excluye la fecha), 7..365.
- Banda: media, desvio, P5/P50/P95, min/max; z-score; percentil de la oferta;
  cambio % vs la ultima oferta; z por mismo dia de la semana (n >= 4).
- Flags: `ok`, `warn` (|z| >= 2), `alert` (|z| >= 3). Historia constante
  (desvio 0): z indefinido, cualquier cambio > 0.5% se marca `changed`.
- Estados sin flag: `insufficient_history` (< 5 dias), `no_offer` (se pidio la
  oferta publicada y no existe).
- `price_cop_mwh = null` audita la oferta ya publicada; con valor, una candidata.

## API
`POST /market/offer-audit` `{date, window_days, offers: [{resource, price_cop_mwh|null}]}`
(1..50 ofertas). Frontend: pagina `/offers` (pegar lineas `RECURSO, precio`).

## Limites
- No se verifica que el recurso pertenezca al usuario (la oferta es publica en XM).
- Con muchos dias sin publicar (rezago ~1 mes de `PrecOferDesp`) la ventana
  reciente puede estar vacia -> `insufficient_history`.
- Probado con fixture sintetico y datos armados a mano, no con descargas reales.
- El flag es sensible a regimenes: un cambio legitimo de costo (combustible)
  se vera como desviacion; la herramienta senala, no juzga.
