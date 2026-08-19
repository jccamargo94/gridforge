---
title: "Hoja de ruta"
layout: default
---

# Hoja de ruta para convertir el modelo de despacho en aplicacion

## Proposito del proyecto

Este repositorio busca replicar, con fines academicos, el proceso de despacho
electrico colombiano con suficiente fidelidad para estudiar:

1. El predespacho ideal, con menor cantidad de restricciones, y su precio
   marginal de operacion frente a referencias publicadas por XM.
2. El despacho ideal, con restricciones adicionales, como aproximacion al
   proceso que determina el precio real de bolsa.
3. El efecto de incorporar almacenamiento BESS bajo distintos niveles de
   penetracion y distintas reglas de participacion en el mercado.

El objetivo de la escalada es pasar de notebooks y scripts ejecutados
manualmente a una aplicacion reproducible, dockerizada, con frontend, backend,
ejecucion por lotes, escenarios configurables y trazabilidad de resultados.

## Estado actual del repositorio

El proyecto ya tiene una primera extraccion hacia una aplicacion Python:

- `app/model/`: modelo Pyomo de unit commitment/despacho.
- `app/pipeline/`: construccion de casos, ejecucion, guardado y evaluacion.
- `app/data/`: carga, descarga y parsing de insumos XM.
- `app/cli.py`: CLI Typer ejecutable con `python -m app run`.
- `tests/`: pruebas unitarias para piezas puras y orquestacion basica.
- `notebooks/*.ipynb`: notebooks exploratorios para descarga, comparaciones y graficas.

La arquitectura actual ya separa parcialmente tres capas:

- Datos: insumos XM, CSV locales, OFEI, condiciones iniciales, precios reales.
- Modelo: formulacion Pyomo y restricciones.
- Pipeline: construir caso, resolver, extraer precios/despacho y medir error.

La brecha principal no es solo tecnica sino de producto: aun falta convertir
esas piezas en una aplicacion operable donde los usuarios puedan configurar
fechas, escenarios, modos BESS, ejecuciones y comparaciones sin editar notebooks.

## Modelos y escenarios objetivo

### 1. Predespacho ideal

Caso base con menor cantidad de restricciones. Debe servir para comparar el
precio marginal del modelo contra la referencia de XM para predespacho y para
crear una linea base computacional rapida.

En el codigo actual corresponde a:

- `preideal`
- `bess_preideal`
- `bess_preideal_resource`

### 2. Despacho ideal

Caso con restricciones adicionales, especialmente restricciones termicas como
rampas, minimos de permanencia, arranques y apagados. Debe ser el principal
modelo para comparar contra precio de bolsa historico cuando los insumos sean
suficientes.

En el codigo actual corresponde a:

- `ideal`
- `bess_ideal`
- `bess_ideal_resource`

### 3. Participacion BESS

La aplicacion debe soportar tres modos conceptuales:

| modo | descripcion | estado en codigo |
| --- | --- | --- |
| Arbitraje independiente | La bateria oferta precio de carga y descarga. Su operacion depende de esos precios y del despacho. | Parcialmente representado por `bess_preideal` y `bess_ideal`. |
| Activo de red / operador | La bateria es optimizada por el operador del sistema y remunerada por energia cargada/descargada. | Parcialmente representado por `bess_preideal_resource` y `bess_ideal_resource`. |
| Generador | La bateria se comporta como recurso/generador que oferta precio de descarga. | Pendiente de formalizar como modo separado. |

La siguiente iteracion debe convertir estos modos en una configuracion explicita,
no en convenciones implicitas dentro del nombre del `dispatch_type`.

## Validacion historica y pronostico operativo

Aunque no sea el alcance inmediato, la aplicacion debe dejar preparada la ruta
para dos tipos de uso:

### Backtesting

Reproducir fechas historicas con insumos reales disponibles y comparar:

- precio marginal modelo vs precio de bolsa o referencia XM;
- despacho por recurso vs despacho real/preideal publicado;
- error por hora, por dia, por mes y por tipo de tecnologia;
- sensibilidad del precio ante penetracion BESS.

Metricas recomendadas:

- MAE y RMSE en COP/kWh;
- bias para detectar sesgo sistematico;
- WAPE y sMAPE para evitar problemas de MAPE cuando el precio se acerca a cero;
- error por bloque horario, especialmente punta/no punta.

### Escenarios hacia adelante

Para ejecutar semanas futuras se requieren supuestos:

- Precios de oferta: usar historicos reales por recurso, con estrategias como
  promedio movil, mediana por dia-tipo/hora, percentiles o modelos robustos por
  tecnologia. Como base inicial se recomienda una mediana movil por recurso y
  dia de semana, con fallback por tecnologia.
- Disponibilidad: usar un baseline seasonal-naive por recurso. Como primera
  version, repetir disponibilidad de la misma hora y mismo tipo de dia de
  semanas previas, con limites por capacidad registrada. Luego se puede pasar a
  modelos probabilisticos por recurso/tecnologia.
- Demanda: consumir forecast publicado cuando exista. Si no existe, usar un
  baseline horario por dia-tipo con ajuste por tendencia reciente.

El pronostico no debe mezclarse con el modelo de despacho. Debe ser un modulo
separado que produzca un paquete de insumos versionado para el solver.

## Arquitectura objetivo

La aplicacion dockerizada deberia evolucionar hacia estos servicios:

| componente | responsabilidad |
| --- | --- |
| Frontend | Configurar ejecuciones, escenarios BESS, fechas, ver progreso y resultados. |
| Backend API | Exponer casos, ejecuciones, resultados, metricas, insumos y escenarios. |
| Worker | Ejecutar descargas, ETL, construccion de caso, solver y evaluacion. |
| Base de datos | Persistir ejecuciones, configuraciones, metadatos, metricas y estado. |
| Storage de archivos | Guardar insumos XM, artefactos intermedios, CSVs y resultados pesados. |
| Solver image | Imagen reproducible con Python, Pyomo y solver disponible. |

Separacion recomendada:

- `app/` mantiene la libreria de dominio y el CLI.
- `services/api/` contendria la API HTTP.
- `services/worker/` contendria tareas asincronas.
- `frontend/` contendria la interfaz.
- `docker/` o `deploy/` contendria compose, Dockerfiles y configuracion.

## Modelo de datos minimo

Entidades iniciales para la app:

- `Case`: fecha, tipo de despacho, fuente de insumos, solver, version del codigo.
- `Scenario`: parametros BESS, modo de participacion, nivel de penetracion.
- `Run`: ejecucion concreta, estado, tiempos, logs, errores.
- `InputArtifact`: archivo o tabla usada como insumo, con fuente y checksum.
- `ResultArtifact`: precios, despacho, SOC BESS, metricas y graficas derivadas.
- `MetricSet`: MAE, RMSE, bias, WAPE, sMAPE y metricas por bloque horario.

## Fases de implementacion

### Fase 0: Inventario y estabilizacion

- Documentar notebooks, scripts y modulos actuales.
- Verificar `case_builder` con datos reales y fixtures doradas.
- Ejecutar pruebas y corregir fallas basicas.
- Definir una convencion unica de unidades y nombres de variables.

### Fase 1: Libreria confiable y CLI completo

- Completar comandos `fetch`, `run`, `evaluate`, `compare`.
- Agregar configuracion de escenarios BESS por archivo YAML/JSON.
- Guardar tambien resultados BESS: carga, descarga, SOC e ingresos/costos.
- Agregar resumen consolidado por corrida.

### Fase 2: Docker y ejecucion reproducible

- Crear `Dockerfile` con solver instalado.
- Crear `docker-compose.yml` con volumen de datos.
- Separar dependencias runtime de notebooks.
- Agregar smoke test dentro del contenedor.

### Fase 3: Backend API y persistencia

- Crear API para registrar escenarios y lanzar ejecuciones.
- Persistir estado y metadatos en base de datos.
- Mover ejecuciones largas a worker asincrono.
- Exponer resultados como tablas descargables y endpoints JSON.

### Fase 4: Frontend operativo

- Pantalla de ejecuciones.
- Configurador de escenario BESS.
- Comparador de precios y metricas.
- Visualizacion de despacho por recurso/tecnologia.
- Explorador de artefactos y logs.

### Fase 5: Forecast y escenarios futuros

- Implementar baselines de precio de oferta, disponibilidad y demanda.
- Versionar supuestos usados por cada corrida.
- Comparar estrategias de forecast en backtesting.
- Permitir ejecuciones para semanas futuras con advertencias explicitas sobre
  supuestos.

## Riesgos tecnicos principales

- La construccion de casos historicos aun necesita validacion end-to-end contra
  datos reales.
- Las reglas BESS actuales deben auditarse para confirmar que cada modo
  economico corresponde exactamente a la formulacion esperada.
- Las ofertas y disponibilidades futuras son supuestos; deben estar separadas y
  etiquetadas para no confundirse con datos reales.
- El solver puede dominar los tiempos de ejecucion; la app debe contemplar
  colas, cancelacion y seguimiento de progreso.
- Los insumos XM cambian de formato o disponibilidad; conviene guardar copias
  locales con checksum y fecha de descarga.

## Proxima decision de diseno

Antes de implementar frontend/backend, conviene cerrar la interfaz de dominio:

1. `DispatchCase`: que fecha y que tipo de despacho se corre.
2. `BessScenario`: cuantos MW/MWh, eficiencia, SOC inicial/final, modo de
   mercado y precios de oferta.
3. `InputPack`: si los insumos son historicos reales, descargados en vivo o
   pronosticados.
4. `RunResult`: precios, despacho, BESS, metricas, logs y errores.

Cuando estas cuatro interfaces sean estables, el salto a API, worker y frontend
sera mucho menos riesgoso.

## Ideas de portafolio (backlog priorizado)

Backlog paralelo a las fases numeradas, salido de una sesion de brainstorming
(2026-08-14) enfocada en que features conviene agregar para demostrar
habilidades de programacion, OR, mercado electrico colombiano y desarrollo
agentic/RAG. No son fases secuenciales del producto — son items independientes,
priorizados por (ejes de portafolio cubiertos) x (demostrable sin datos
privados) / (costo de build).

Contexto que valida las prioridades: el pricing run ya hace fix-and-resolve
correcto (fijar binarios MILP, resolver LP, leer dual de `power_balance` en
`app/model/model.py:324-345`) — el precio marginal es defendible, no hackeado.
Eso hace que un agente que explique corridas contra esa base sea el item de
mayor señal, y no una feature que primero tenga que arreglar el pricing.

| # | Item | Ejes | Effort | Issue |
| --- | --- | --- | --- | --- |
| 1 | Agente "explica esta corrida" (tool-calling sobre artefactos) | OR, mercado, agentic, ingenieria | M (3-5d) | [#56](https://github.com/jccamargo94/gridforge/issues/56) |
| 2 | Copiloto RAG sobre documentacion propia del proyecto | RAG, ingenieria | S (1-2d) | [#57](https://github.com/jccamargo94/gridforge/issues/57) |
| 3 | Harness de benchmark de formulaciones (rampas/min-up-down) | OR | M (3-4d) | [#58](https://github.com/jccamargo94/gridforge/issues/58) |
| 4 | BESS: formalizar modo "generador" | mercado, OR | L (5-8d) | [#59](https://github.com/jccamargo94/gridforge/issues/59) |
| 5 | Casos de estudio con fechas reales en GitHub Pages | mercado, storytelling | S (1-2d) | [#60](https://github.com/jccamargo94/gridforge/issues/60) |
| 6 | Pagina "como se construyo esto" (SDD real + skills) | agentic dev | XS (0.5-1d) | [#61](https://github.com/jccamargo94/gridforge/issues/61) |

Item 1 es el flagship: es el unico que cubre los cuatro ejes a la vez y sus
respuestas son verificables contra la solucion LP, no solo plausibles. Item 2
es el unico que demuestra RAG especificamente (retrieval sobre corpus no
estructurado) — item 1 es tool-calling sobre datos estructurados, tecnica
distinta a proposito para mostrar ambas. Items 5 y 6 son los de menor costo:
5 resuelve que `data/` este git-ignored (un reviewer sin datos XM reales nunca
ve el modelo contra precio de bolsa real), 6 hace visible el desarrollo
agentic que ya existe en `.superpowers/sdd/` y `.agents/skills/` pero que hoy
nadie fuera del repo puede ver.

Descartado explicitamente: RAG regulatorio (resoluciones CREG, acuerdos CNO).
El corpus publico no esta verificado como fetchable de forma confiable y el
riesgo de alucinar citas legales es alto — el copiloto de item 2 cubre el eje
RAG sin ese riesgo, acotado a documentacion propia del repo.

Detalle completo de cada item (plan de implementacion, riesgos, prerequisitos)
en su issue correspondiente.
