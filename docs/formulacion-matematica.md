---
title: "Formulación matemática"
layout: default
---

# Formulación matemática del despacho

El modelo resuelve un **unit commitment** de 24 horas: decide qué generadores
operar, a qué nivel y cuándo arrancarlos/apagarlos para satisfacer la demanda al
menor costo, sujeto a restricciones técnicas. Cuando se incorporan baterías BESS,
el problema se extiende con la operación de almacenamiento.

El proyecto implementa **dos niveles de despacho**:

- **Preideal**: demanda del pronóstico PrId (día previo) y disponibilidad
  declarada. Se compara contra el MPO del predespacho ideal (archivo iMAR).
- **Ideal**: demanda comercial real (demaCome) y disponibilidad comercial real
  (dispo_come). Es la aproximación al proceso que determina el **precio de
  bolsa**, y se compara contra el precio real de bolsa (PrecBolsNaci) y el MPO de
  iMAR.

## Variables de decisión

- $p_{g,t} \ge 0$: generación efectiva del generador $g$ en el intervalo $t$ (MW).
- $z_{g,t} \in \{0,1\}$: indica si el generador $g$ está en servicio en $t$.
- $z^{up}_{g,t}, z^{down}_{g,t} \in \{0,1\}$: señales de arranque y apagado.
- Para BESS: $c_{b,t}, d_{b,t}, soc_{b,t} \ge 0$ y $\delta^{ch}_{b,t}, \delta^{dis}_{b,t} \in \{0,1\}$.

## Función objetivo

El objetivo es minimizar el costo de generación más el costo de arranque:

$$\min \sum_{g,t} \beta_g p_{g,t} + \sum_{g,t} c_g^{start} z^{up}_{g,t}$$

donde $\beta_g$ es el precio de oferta del generador (COP/MWh) y $c_g^{start}$ el
costo de arranque en frío (COP). En los modos BESS orientados al bienestar
social, el objetivo incorpora también los costos/beneficios de carga y descarga
del almacenamiento.

## Restricciones principales

### Balance de potencia

$$\sum_{g} p_{g,t} + \sum_b \left(d_{b,t} - c_{b,t}\right) = D_t, \qquad \forall t$$

El dual de esta restricción es el **precio marginal de operación** (MPO).

### Rango operativo por generador

$$P^{min}_{g} z_{g,t} \le p_{g,t} \le P^{max}_{g,t} z_{g,t}, \qquad \forall g,t$$

donde $P^{max}_{g,t}$ es la disponibilidad declarada/comercial del generador en
cada hora.

### Rampas y permanencia mínima

$$p_{g,t} - p_{g,t-1} \le RU_g, \qquad p_{g,t-1} - p_{g,t} \le RD_g, \qquad \forall g,t$$

y las restricciones de tiempo mínimo en línea y de arranque/apagado aseguran
consistencia operativa entre períodos consecutivos.

## Formulación de BESS

Para cada batería $b$ y periodo $t$, el estado de carga evoluciona como:

$$soc_{b,t} = soc_{b,t-1} + \eta^{ch}_{b} c_{b,t} - \frac{d_{b,t}}{\eta^{dis}_{b}}$$

con límites de potencia y de estado de carga:

$$0 \le c_{b,t} \le C^{max}_{b} \delta^{ch}_{b,t}, \qquad 0 \le d_{b,t} \le D^{max}_{b} \delta^{dis}_{b,t}$$

$$SOC^{min}_{b} \le soc_{b,t} \le SOC^{max}_{b}$$

Además, se prohíbe cargar y descargar simultáneamente: $\delta^{ch}_{b,t} + \delta^{dis}_{b,t} \le 1$.

## Precio marginal

El MPO se obtiene del **dual del balance de potencia** después de resolver una
segunda corrida LP con las variables binarias fijadas al valor óptimo
(fix-and-resolve). Esta práctica evita leer precios marginales de una solución
MILP, donde los duales no son válidos.

## Referencia de comparación

| Nivel | Demanda | Disponibilidad | Referencia de precio |
|---|---|---|---|
| Preideal | Pronóstico PrId | Declarada | MPO de iMAR |
| Ideal | Comercial real (demaCome) | Comercial real (dispo_come) | **Precio de bolsa real** (PrecBolsNaci) y MPO de iMAR |

Para fechas recientes donde la demanda/disponibilidad comercial real aún no se
publica (rezago de ~3 días), el modo ideal cae al pronóstico PrId y a la
disponibilidad declarada, **emitiendo una advertencia** para distinguir la corrida
de una que usó datos reales.
