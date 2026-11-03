# Posicion competitiva / orden de merito (issue #82) - Diseno

Rama: `fase9a-posicion-competitiva`. Fecha: 2026-11-03.

## Que resuelve
Un agente ve donde queda su planta en el orden de merito del sistema cada hora
y como se mueve en el tiempo, usando solo datos observados (sin `case_builder`,
sin Pyomo).

## Datos y unidades (verificadas contra `case_builder.py`, no de memoria)
- `dispo_declarada_{year}.csv`: horaria, `dispo` en kW (x1e-3 -> MW), trae `gen_type`.
- `ofertas_{year}.csv`: **un precio por recurso por dia** (`PrecOferDesp`,
  `Value` en COP/kWh, x1e3 -> COP/MWh), no horario.
- `demaCome_{year}.csv`: `dema` x1e-3 -> MW.

## Calculo (`app/market/merit.py`)
Por hora: recursos con `dispo > 0` y oferta ese dia, ordenados por precio.
`rank` = 1 + # de ofertas estrictamente mas baratas; `cum_ahead_mw` = MW con
oferta estrictamente mas barata (los empates comparten posicion, sin desempate
arbitrario); `in_merit` = `cum_ahead_mw < demanda`. Se reporta tambien el
precio de la oferta que cubre la demanda (`clearing_price`) y los MW
declarados sin oferta (excluidos).

## Privacidad (limite del issue)
Nunca se devuelve la oferta de un rival por nombre. Los rivales salen
agregados por tecnologia (n, MW, precio medio ponderado por capacidad, MW en
merito); un grupo con menos de 3 recursos se pliega a `OTROS` y, si aun asi
queda con menos de 3, se oculta.

## API
- `GET /market/merit-position?date=&own=A,B`
- `GET /market/position-series?start=&end=&own=A,B` (maximo 92 dias)
`DATA_DIR` (default `data`) apunta a los year CSVs.

## Decisiones y limites conocidos
- `own` se pasa por parametro: no hay mapeo agente->recurso en los datos y hoy
  no existe un flujo para crear tenants. Persistirlo (tabla por tenant) queda
  para cuando haya aprovisionamiento de tenants.
- Como no se puede verificar que `own` sea del usuario, un usuario podria
  pedir la posicion de cualquier planta. Las ofertas son publicas en XM; la
  politica de agregados cubre la vista de mercado, no impide eso.
- Agregado por **tecnologia** solamente; por **zona** requiere cruzar con la
  topologia (`app/data/topology`) y queda como siguiente paso.
- Sin datos reales validados: probado con el fixture sintetico y datos
  construidos a mano; no se corrio contra descargas reales de XM.
- Mes sin publicar: `PrecOferDesp` tiene ~1 mes de rezago, esos dias dan
  `n_priced = 0` / 404 si falta el CSV del ano.
