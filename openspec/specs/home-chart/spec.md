# Especificacion home-chart

## Proposito

Home chart-first en `/`: serie diaria de precios (TX1, MPO XM, ideal liquidado/provisional, preideal) con seleccion de dia, panel inline de detalle horario, zoom por rango (Brush) y tooltip fijable; la navegacion a `/runs/[id]` es explicita desde el panel. El backend `GET /chart/series` sirve el contrato diario (9 claves por dia, `days` 1..90, default 30) y los 5 arrays horarios (24 posiciones, `null` en gaps) derivados de la tabla `hourly_series` (REQ-HC-01, REQ-HC-02). Los requirements de frontend de este spec (issue #90) permanecen vigentes.

## No objetivos

LMP, agregacion semanal, nueva vista de detalle, nav movil, acceso anonimo. `PriceSeriesChart` NO se reutiliza (dominio hora); solo sus patrones. El overlay horario deja de ser no-objetivo: se sirve en un panel inline del Home (ver requirement de detalle horario). Ya no aplica el no-objetivo "cambio backend": time-series-db modifico `GET /chart/series` (REQ-HC-01, REQ-HC-02) manteniendo el contrato diario.

## Requirements

### Requirement: Home chart-first en `/`

El sistema MUST renderizar Home en `/` sin redireccion y mantener `/runs` como pagina manual.

#### Scenario: Visita autenticada a `/`

- GIVEN sesion valida
- WHEN abre `/`
- THEN ve titulo, selector, grafica y navegacion con entrada Home

#### Scenario: `/runs` sigue accesible

- GIVEN sesion valida
- WHEN abre `/runs`
- THEN ve solo ejecuciones manuales (ver requisito de filtro)

### Requirement: Serie compuesta de 5 lineas nulables

El sistema MUST dibujar un `LineChart` con dominio fecha y 5 lineas (`bolsa_tx1`, `mpo_xm`, `ideal_settled`, `ideal_provisional`, `preideal`) con `connectNulls={false}`; todo `null` MUST ser gap, nunca cero.

#### Scenario: Dia sin TX1 publicado

- GIVEN fila con `bolsa_tx1=null`
- WHEN renderiza la serie
- THEN esa linea muestra gap y las demas continuan

#### Scenario: Cola con nulos (lag normal)

- GIVEN solo los ultimos dias en `null`
- WHEN renderiza
- THEN muestra tramo parcial mas aviso, no estado vacio

### Requirement: Selector de ventana 7/30/90

El sistema MUST ofrecer 7/30/90 con default 30 y una sola consulta `getChartSeries(days)` por seleccion.

#### Scenario: Carga inicial

- GIVEN Home sin seleccion previa
- WHEN monta
- THEN pide `days=30` y marca 30 como activo

#### Scenario: Cambio de ventana

- GIVEN serie de 30 dias visible
- WHEN elige 7
- THEN refetchea con `days=7` (vitest: mock fetch + assert query)

### Requirement: Estados carga/vacio/error y aviso TX1

El sistema MUST mostrar carga (`home.loading`), vacio (`home.empty`) solo si toda la ventana es nula, error con `role="alert"` (`home.error`), y caption permanente del lag TX1 (`home.tx1Lag`).

#### Scenario: Ventana totalmente vacia

- GIVEN todas las series `null` en la ventana
- WHEN resuelve la consulta
- THEN muestra estado vacio Zap, no grafica rota

#### Scenario: Fallo de red

- GIVEN `GET /chart/series` responde 500
- WHEN resuelve la consulta
- THEN muestra `home.error` en `role="alert"` con reintento

### Requirement: Drill-down explicito al mejor run del dia

El sistema MUST seleccionar el dia al hacer click en la grafica (sin navegar) y MUST navegar a `/runs/[id]` solo desde la accion explicita "ver run" del panel horario, usando el mejor `*_run_id` del dia con prioridad `ideal_settled` > `ideal_provisional` > `preideal`; un dia sin ids MUST NOT ofrecer la accion. Asimetria backend: `preideal` es carril unico (settled gana; el provisional se vuelve inalcanzable).

#### Scenario: Dia con ideal liquidado

- GIVEN fila con `ideal_settled_run_id` e `ideal_provisional_run_id`
- WHEN el usuario abre el panel del dia y activa "ver run"
- THEN `router.push("/runs/<ideal_settled_run_id>")`

#### Scenario: Dia sin runs

- GIVEN fila con los tres `*_run_id` en `null`
- WHEN el usuario abre el panel del dia
- THEN no ve la accion "ver run" y no navega

### Requirement: Detalle horario del dia en panel inline

El sistema MUST abrir un panel inline debajo de la grafica al seleccionar un dia, con hasta 24 puntos horarios (hora Bogota) por cada serie visible (estado `hidden` de la leyenda respetado). Todo `null` horario MUST ser gap, nunca cero. El panel MUST poder cerrarse (accion de cierre o segundo click en el mismo dia) y cambiar de dia (click en otro dia). Si no hay ningun valor horario visible, MUST mostrar un mensaje de vacio en lugar de una grafica rota.

#### Scenario: Dia con detalle horario

- GIVEN fila con `*_hourly` de 24 posiciones
- WHEN se selecciona el dia
- THEN el panel dibuja 24 puntos por serie visible y respeta los `null` como gaps

#### Scenario: Serie oculta en la leyenda

- GIVEN una serie oculta con `hidden`
- WHEN se abre el panel
- THEN esa serie no aparece en el detalle horario

#### Scenario: Panel sin datos horarios

- GIVEN un dia cuyos `*_hourly` visibles son todos `null`
- WHEN se abre el panel
- THEN muestra el mensaje de vacio horario, no una grafica vacia

#### Scenario: Cierre del panel

- GIVEN panel abierto
- WHEN el usuario activa cerrar o hace click de nuevo en el mismo dia
- THEN el panel se oculta y el dia queda sin seleccion

### Requirement: Zoom por rango con Brush sincronizado

El sistema MUST ofrecer un `Brush` de recharts que lea y escriba el mismo rango visible que la rueda y el pan; arrastrar el Brush MUST actualizar la ventana visible, la rueda y el pan MUST reflejarse en el Brush, y el doble click MUST restablecer la ventana completa. La ventana MUST respetar el minimo de 4 puntos. Las interacciones del Brush MUST NOT disparar el pan del wrapper ni seleccionar dias.

#### Scenario: Arrastrar el Brush

- GIVEN ventana completa de la serie
- WHEN el usuario arrastra el Brush a un subrango
- THEN la grafica muestra ese subrango y `isZoomed` es verdadero

#### Scenario: Rueda sincronizada con el Brush

- GIVEN una ventana reducida con el Brush
- WHEN el usuario usa la rueda
- THEN el Brush refleja la nueva ventana visible

#### Scenario: Minimo de ventana

- GIVEN ventana completa
- WHEN el Brush selecciona menos de 4 puntos
- THEN la ventana se ajusta al minimo de 4

#### Scenario: Pan sobre el Brush

- GIVEN una ventana con zoom
- WHEN el usuario arrastra un control del Brush
- THEN la ventana solo cambia por la accion del Brush, no por el pan del wrapper

### Requirement: Tooltip fijable

El sistema MUST fijar el tooltip del dia con un click en un punto o linea (sobrevive al mouse-out) y MUST soltarlo con un segundo click en el mismo dia o con un click fuera del bloque del Home. Mientras no haya dia fijado, el tooltip MUST seguir el hover. El cursor del tooltip SHOULD dibujarse como crosshair con el estilo del tema.

#### Scenario: Fijar el tooltip

- GIVEN tooltip visible por hover
- WHEN el usuario hace click en el dia
- THEN el tooltip queda visible aunque el mouse salga de la grafica

#### Scenario: Soltar el tooltip

- GIVEN tooltip fijado
- WHEN el usuario hace click de nuevo en el mismo dia o fuera del bloque del Home
- THEN el tooltip deja de estar fijado y vuelve al hover

### Requirement: `/runs` solo manuales

El sistema MUST filtrar en cliente las corridas diarias publicas (`visibility`/`input_grade`) de tabla y contadores.

#### Scenario: Lista mixta

- GIVEN respuesta con run manual y run `public`/`settled` diario
- WHEN renderiza `/runs`
- THEN solo el manual aparece y los stats lo cuentan solo a el

### Requirement: i18n home.* es+en

El sistema MUST resolver estas claves en ambos idiomas (es sin tildes): `home.title`="Precios del mercado"/"Market prices", `home.subtitle`="Bolsa real, MPO de XM y simulaciones del modelo por dia"/"Real bolsa, XM MPO and model simulations per day", series `home.tx1`="Bolsa real (TX1)"/"Real bolsa (TX1)", `home.mpo`="MPO XM (iMAR)"/"XM MPO (iMAR)", `home.idealSettled`="Ideal liquidado"/"Settled ideal", `home.idealProv`="Ideal provisional"/"Provisional ideal", `home.preideal`="Preideal"/"Preideal", `home.loading`="Cargando serie..."/"Loading series...", `home.empty`="Sin datos de serie todavia."/"No series data yet.", `home.error`="No se pudo cargar la serie."/"Could not load the series.", `home.tx1Lag`="TX1 publica con 2-4 dias de retraso."/"TX1 publishes with a 2-4 day lag.", `home.hourly`="Detalle horario"/"Hourly detail", `home.hourlyEmpty`="Sin detalle horario para este dia."/"No hourly detail for this day.", `home.viewRun`="Ver run"/"View run", `home.close`="Cerrar"/"Close", `sidebar.home`="Inicio"/"Home".

#### Scenario: Cambio de idioma

- GIVEN `gridforge-lang=en`
- WHEN abre `/`
- THEN ve copy en ingles; con `es` ve copy sin tildes

### Requirement: REQ-HC-01 Promedio diario derivado de hourly_series

El backend `GET /chart/series` SHALL derivar el promedio diario de cada serie de precios desde la tabla `hourly_series` (unica fuente de verdad) en lugar de colapsar CSVs por request. El promedio diario de un (serie, dia) SHALL ser la media de las 24 filas horarias de la fuente ganadora del dia (mismo criterio de prioridad de run que hoy: ideal liquidado > provisional > preideal).

#### Scenario: SCN-HC-01-01 Promedio diario consistente con lo horario

- GIVEN 24 filas horarias publicas de `bolsa_tx1` para el dia D
- WHEN se pide `GET /chart/series` para D
- THEN el valor diario de `bolsa_tx1` es la media de las 24 filas

#### Scenario: SCN-HC-01-02 Dia sin datos no inventa ceros

- GIVEN dia D sin filas en `hourly_series` para una serie
- WHEN se pide `GET /chart/series` para D
- THEN esa clave queda `null` (gap), nunca cero

### Requirement: REQ-HC-02 Valores horarios disponibles

El backend SHALL exponer los valores horarios (hasta 24 por dia) de las series de precios servidas al Home, publicas y por tenant, manteniendo el contrato diario existente (claves, `days` 1..90). Valores horarios de otra fuente que no sea `hourly_series` SHALL NOT servirse.

#### Scenario: SCN-HC-02-01 Respuesta horaria publica

- GIVEN 24 filas publicas de `mpo_xm` para el dia D
- WHEN se piden los valores horarios de D
- THEN la respuesta expone 24 valores horarios mas el promedio diario

#### Scenario: SCN-HC-02-02 Aislamiento por tenant

- GIVEN filas publicas y filas del tenant A en `hourly_series`
- WHEN un miembro de A pide los valores horarios
- THEN recibe filas publicas y de A; ninguna fila de otro tenant
