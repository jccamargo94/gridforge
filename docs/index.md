---
title: "Inicio"
layout: default
---

<div class="hero">
  <div class="hero-logo">
    <img src="{{ "/assets/logo.svg" | relative_url }}" alt="GridForge logo" width="72" height="72">
  </div>
  <div>
    <h1>GridForge</h1>
    <p class="lead">Modelo académico de despacho eléctrico colombiano, validado contra datos reales de XM.</p>
    <p class="badges">
      <span class="badge badge-accent">Python 3.12</span>
      <span class="badge badge-accent">Pyomo · CBC</span>
      <span class="badge">FastAPI</span>
      <span class="badge">Next.js</span>
      <span class="badge">BESS</span>
    </p>
  </div>
</div>

GridForge es un modelo de **unit commitment** en Pyomo que aproxima el despacho
económico del sistema eléctrico colombiano, reproduce el **precio de bolsa**
publicado por [XM](https://www.xm.com.co/) y evalúa el impacto de incorporar
sistemas de almacenamiento en batería (BESS). Se distribuye como librería Python
+ CLI Typer, con backend FastAPI, worker de ejecución y frontend Next.js.

## Qué hace

- Construye casos de despacho (predespacho ideal y despacho ideal) desde los
  insumos públicos de XM: OFEI, condiciones iniciales, demanda, disponibilidad y
  ofertas.
- Resuelve un MILP de unit commitment con restricciones térmicas (rampas, tiempos
  mínimos, arranques) y calcula el **precio marginal** mediante un resolve LP con
  variables binarias fijadas.
- Compara el resultado contra los valores reales publicados por XM: **precio de
  bolsa** (PrecBolsNaci) y **MPO del predespacho ideal** (iMAR), con métricas de
  precio y despacho.
- Incorpora escenarios BESS declarativos bajo distintos niveles de penetración y
  modos de participación.
- Modela la red de transmisión del SIN (zonas/subáreas, ramas y capacidades) y
  resuelve un despacho **nodal** vía DC-OPF para calcular precios locacionales
  (**LMP**) y congestión entre zonas.

## Variantes de despacho

| Nivel | Demanda | Disponibilidad | Comparación |
|---|---|---|---|
| **Preideal** | Pronóstico PrId (día previo) | Disponibilidad declarada | MPO de iMAR |
| **Ideal** | Demanda comercial real (demaCome) | Disponibilidad comercial real (dispo_come) | **Precio de bolsa real** (PrecBolsNaci) y MPO de iMAR |
| **Nodal (LMP)** | Comercial real o pronóstico | Comercial real o declarada | Red nodal (DC-OPF) — precio locacional y congestión por zona |

Para fechas recientes, donde XM aún no publica la demanda/disponibilidad
comercial real (rezago de ~3 días), el modo ideal cae automáticamente al
pronóstico PrId y a la disponibilidad declarada, **con una advertencia explícita**
para que el usuario sepa que la corrida usó datos pronosticados.

## Resultados recientes (despacho ideal)

Corridas de validación del modo ideal contra el precio de bolsa real:

| Fecha | Referencia | RMSE precio (COP/MWh) | MAE precio (COP/MWh) | MAE despacho (MW) |
|---|---|---|---|---|
| 2026-02-10 | Bolsa real | 114,227 | 44,961 | 10.3 |
| 2026-05-15 | Bolsa real | 43,435 | 26,636 | 10.8 |
| 2026-08-02 | Bolsa real | 299,640 | 284,340 | 8.8 |
| 2026-08-11 | MPO iMAR* | 970,462 | 970,023 | 16.5 |

*La bolsa real de 2026-08-11 aún no está publicada; se comparó contra el MPO de
iMAR con datos pronosticados (advertencias activas). El error de precio en fechas
recientes es consistente con la heurística de ofertas estimadas.

## Documentación

<div class="card-grid">
  <div class="card">
    <h3>Formulación matemática</h3>
    <p>Variables, función objetivo, restricciones y procedimiento de precio marginal del modelo.</p>
    <p><a href="{{ "/formulacion-matematica.html" | relative_url }}">Ver →</a></p>
  </div>
  <div class="card">
    <h3>Hoja de ruta</h3>
    <p>Fases de implementación, estado actual y objetivos del proyecto.</p>
    <p><a href="{{ "/roadmap-aplicacion-despacho.html" | relative_url }}">Ver →</a></p>
  </div>
  <div class="card">
    <h3>README del repositorio</h3>
    <p>Instalación, datos requeridos, estructura y guía de uso completa.</p>
    <p><a href="https://github.com/jccamargo94/gridforge">Ver →</a></p>
  </div>
</div>

## Cómo navegar el proyecto

- `app/model/` — modelo Pyomo (preideal/ideal), variables y restricciones.
- `app/nodal/` — motor de despacho nodal (DC-OPF vía EGRET), precios
  locacionales y liquidación de congestión.
- `app/pipeline/` — construcción del caso, ejecución, guardado y evaluación.
- `app/data/` — carga, descarga y parsing de insumos XM.
- `app/data/topology/` — scraper PARATEC/SIMEM que construye la red nodal
  (zonas, ramas, capacidades).
- `services/api/` — API FastAPI para ejecutar y consultar corridas.
- `services/worker/` — worker de polling que reclama y ejecuta corridas.
- `frontend/` — interfaz Next.js para crear corridas y visualizar resultados,
  incluyendo el visor de red nodal y el dashboard de precios/congestión.
- `tests/` — suite pytest para validación del pipeline y del CLI.
