# topology-subarea-scope — Diseño

Rama: `fase6c-topologia-subarea` (a crear). Repo: `gridforge`, `develop`.
Fecha: 2026-08-20.

## 1. Contexto

`scrape-topology` (fase6b, merged a `develop`) construye una `NodalNetwork`
con **una zona por subestación PARATEC** (500+ zonas). Al correr contra datos
reales (`--date 2026-08-02`), falla: 72 de 927 líneas tienen un extremo
(`from_zone`/`to_zone`, obtenido de partir `line.subStation` en `" - "`) que
no es el `elementName` de ninguna subestación — ver
`lmp-zone-verification.md` (raíz del repo) para el diagnóstico completo y la
evidencia de los 23 strings colgantes distintos.

Investigando ese bug se encontró que la implementación de fase6b se desvía
de dos decisiones ya tomadas en specs anteriores:

- `docs/superpowers/plans/README-nodal.md:9` — "construye una red nodal
  (**zonal, en v1**)".
- `docs/superpowers/specs/2026-08-18-lmp-nodal-market-design.md:218-220` —
  granularidad zonal en v1 es mitigación explícita porque CBC es lento con
  muchas zonas/binarias; escalar a red completa ("full nodal") solo si se
  usa un solver comercial.

fase6b (`docs/superpowers/specs/2026-08-19-paratec-topology-scraper-design.md:118-120`)
implementó zonas = subestación (full nodal) un día después, sin referenciar
esa decisión. Este documento re-escopea a **zonas = subárea operativa**
(21 subáreas domésticas), que es lo que las specs fundacionales pedían, y
deja preparada la interfaz para agregar granularidad de subestación
("node") más adelante detrás del mismo contrato.

**Fuera de alcance de este documento**: implementar el scope `node` (ya
existe como `build_network` actual, se re-envuelve tal cual) y el fix del
bug de spec-deviation en su manejo de referencias colgantes (fase6b spec
§v1 decía "dropear la rama con log"; la implementación actual deja que
pydantic explote sin contexto). Ambos quedan diferidos — a nivel `subarea`
ese bug se vuelve inalcanzable por construcción (ver §3).

## 2. Hallazgos empíricos (verificados en vivo, 2026-08-20)

### 2.1 SIMEM como catálogo ground-truth de áreas/subáreas

`POST https://www.simem.co/backend-files/api/datos-publicos?datasetId=<id>&startDate=<d>&endDate=<d>`
con body `[]`, sin auth, devuelve una lista JSON plana (no envuelta en
`{result:{...}}`). No estaba mapeado en el repo antes de esta sesión.

- `datasetId=841808` → 8 áreas operativas (`CodigoAreaOperativa`,
  `NombreAreaOperativa`, p.ej. "Area Antioquia").
- `datasetId=10F2C9` → 23 subáreas operativas (`CodigoSubAreaOperativa`,
  `NombreSubareaOperativa`, p.ej. "SubArea Antioquia").
- Snapshot republicado en múltiples `Fecha` — deduplicar por nombre.

Verificado: los 21 valores distintos de `subAreaName` presentes en las 509
subestaciones PARATEC (`Substation/SubstationInfo`) son subconjunto exacto
de las 23 subáreas SIMEM (las 2 sobrantes — `Ecuador138`, `No Definida` —
no tienen ninguna subestación real, esperado). **No se requiere un
fetcher SIMEM para este entregable** — la comparación de conjuntos ya
prueba la factibilidad y el campo `subAreaName` de PARATEC es la fuente
operacional real (SIMEM queda como referencia de auditoría, no como
dependencia en el pipeline).

### 2.2 `TransmissionMap/getLines` — fuente de ramas limpia

`GET https://paratecbackend.xm.com.co/mapas/api/TransmissionMap/getLines`
(mismos headers que el resto de PARATEC) devuelve 805 líneas como GeoJSON
`Feature`, con `properties.sub1`/`sub2` (nombre de subestación, texto
estructurado, no requiere split) y `properties.subArea1`/`subArea2`
(código numérico interno 0-19).

Verificado sobre las 805 líneas:
- **100%** de `sub1`/`sub2` matchean exacto contra `elementName` de una
  subestación conocida (0 colgantes).
- El código numérico `subArea1`/`subArea2` mapea **1:1** contra
  `subAreaName` derivado vía `sub1`/`sub2` → subestación (18 códigos
  distintos → 18 subáreas distintas, sin ambigüedad). **No se usa el
  código como fuente de verdad** — se deriva la subárea real vía
  `elementName → subAreaName` (igual que `parse_substations` ya hace); el
  código numérico solo sirve como assert de consistencia interna.
- Las 3 subáreas ausentes en el set de códigos son exactamente las de
  frontera (`Venezuela_Corozo`, `Ecuador230`, `Venezuela_Cuatricentenario`)
  — ya excluidas del modelo doméstico (`build.py:137` actual). Ninguna
  subárea doméstica se pierde.

`getLines` es subconjunto estricto de `Line/getAll` (805 de 927; 0 líneas
en `getLines` que no estén en `Line/getAll`). De las 122 líneas ausentes
en `getLines`, resolviendo ambos extremos del split de `subStation` contra
el índice de subestaciones:
- 67 son intra-subárea (mismo extremo en ambos lados → se fusionan, sin
  pérdida de información relevante a nivel subárea).
- 47 tienen un solo extremo resoluble (spurs a planta/generador, extremo
  no es una subestación de transmisión).
- 6 no resuelven ningún extremo.
- **Solo 2 son inter-subárea reales** — y ambas son interconexión
  `Ecuador230` (frontera, fuera de alcance del modelo doméstico de
  cualquier forma).

**Conclusión**: `TransmissionMap/getLines` es fuente primaria suficiente
para ramas inter-subárea; `Line/getAll` solo aporta relleno de fusión
intra-zona (sin ningún caso de normalización de texto ad-hoc — el split
de `subStation` se sigue usando para el relleno, pero el resultado siempre
se clasifica como intra-zona o se descarta, nunca necesita resolver un
endpoint colgante a una subárea específica de forma ambigua).

## 3. Arquitectura

### 3.1 Interfaz `TopologyBuilder`

```python
# app/data/topology/builders/base.py
class TopologyBuilder(Protocol):
    def build(
        self,
        raw: dict[str, Any],      # salida de fetch.fetch_all()
        demand: dict[str, list[float]],
        *,
        demand_split: str = "capacity",
        reference_zone: str | None = None,
    ) -> NodalNetwork: ...
```

Tres implementaciones, seleccionadas por `--scope`:

| scope | Estado | Zonas | Fuente de ramas |
|---|---|---|---|
| `subarea` (default) | **Este entregable** | 21 subáreas | `TransmissionMap/getLines` + relleno `Line/getAll` |
| `node` | Diferido — envuelve `build_network` actual sin cambios | 500+ subestaciones | `Line/getAll` (bug de spec-deviation queda tal cual, diferido) |
| `area` | Diferido — solo la interfaz, sin implementación | 8 áreas | No hay fuente de líneas a nivel área en PARATEC; requiere agregar subárea→área primero (no cubierto aquí) |

`cli.py::scrape_topology_cmd` gana `--scope subarea|node|area` (default
`subarea`) y despacha al builder correspondiente vía un dict de registro
simple (no factory abstracta — 3 casos conocidos, YAGNI).

### 3.2 `fetch.py`

Agregar `"lines_map": f"{PARATEC_BASE}/mapas/api/TransmissionMap/getLines"`
a `ENDPOINTS`. Mismo mecanismo de cache (`topology/raw/lines_map.json`) que
el resto — `fetch_all` ya itera `ENDPOINTS`, no requiere código nuevo más
allá de la entrada del dict.

### 3.3 `parse.py`

Nueva función `parse_map_lines(payload)`, análoga a `parse_lines` pero para
el payload GeoJSON de `lines_map`:

```python
def parse_map_lines(payload: Any) -> list[dict]:
    """Parse TransmissionMap/getLines GeoJSON into flat line records.

    Returns dicts with sub1/sub2 (substation elementName, exact match —
    no free-text split), reactance/rating/kv. Zone assignment happens in
    build.py via the substation -> subarea index.
    """
```

Campos por record: `name` (`properties.nameLine`), `sub1`, `sub2`,
`rating` (desde `emergencyLimit`/`ratedCurrent` × kV × √3, misma fórmula
que `parse_lines`), `kv` (de `properties.energy`, parsear el primer
número). **`reactance_ohm` no está en el payload de `getLines`**
(propiedades disponibles: `nameLine`, `sub1`, `sub2`, `subArea1/2`,
`energy`, `emergencyLimit`, `ratedCurrent`, `operator`, `color`,
`longitude` — sin reactancia ni `typeLines`; verificado en vivo). Se
resuelve cruzando por nombre exacto contra el índice de `Line/getAll`
(`{l["name"]: l for l in lines}`) — **confirmado: el 100% de los 805
`nameLine` de `getLines` tienen match exacto de `name` en `Line/getAll`**
(las 927 - 805 = 122 líneas exclusivas de `Line/getAll` no tienen
contraparte en `getLines`, pero la relación inversa es completa). No hace
falta fallback adicional.

`parse_lines` (el split de `subStation`) se mantiene sin cambios — lo
sigue usando el scope `node`, y el relleno intra-zona del scope `subarea`
(§3.4).

### 3.4 `build.py` — `build_subarea_network`

Nueva función en `app/data/topology/builders/subarea.py`:

1. **Índice subestación → subárea**: `{s["name"]: s["subarea"] for s in
   subs}` (reusa `parse_substations` sin cambios).
2. **Zonas**: `{s["subarea"] for s in subs} - EXCLUDED` → una `Zone` por
   subárea doméstica (21). `base_kv` = no aplica a nivel subárea real;
   usar un valor representativo (p.ej. 230.0 fijo, documentado) ya que el
   schema lo requiere pero el motor no lo usa para el cálculo de LMP.
3. **Ramas inter-subárea**: para cada línea de `parse_map_lines`, resolver
   `subarea(sub1)`/`subarea(sub2)` vía el índice. Si son distintas →
   candidata a `Branch`. Agrupar por par `(subarea_a, subarea_b)`
   (no ordenado) y combinar eléctricamente: `rating = Σratings`,
   `1/X_total = Σ(1/X_i)`. Mismo criterio para el relleno de
   `Line/getAll` cuando ambos extremos resuelven a subáreas distintas
   (caso real: solo 2, ambos frontera, se excluyen junto con las
   subáreas de frontera).
4. **Relleno intra-zona** (de ambas fuentes, todo lo que NO cae en el
   punto 3): agregado vía la misma combinación eléctrica, pero **no se
   emite como `Branch`** — no aporta al grafo inter-zonal. Se acumula en
   un resumen `{subarea: {"rating_mw": ..., "n_lines": ...}}`.
5. **Generadores**: `zone = subarea del generador` directo (campo
   `subArea` que ya trae el catálogo de capacidad vía `parse_generators`,
   sin `_nearest_zone`/geo — no aplica a esta granularidad).
6. **`demand_shares`**: `demand[subarea]` normalizado a sumar 1.0
   directamente (sin split a subestación — la demanda XM ya viene por
   subárea). Zonas de frontera/`"Total"` del dict `demand` (bug latente
   ya presente en `parse_demand`: `EXCLUDED_SUBAREAS` compara contra
   nombres sin el prefijo `"SubArea "` real del archivo, por lo que hoy
   no excluye nada — inofensivo en `node` scope porque ninguna
   subestación tiene esas subáreas; en `subarea` scope tampoco afecta
   porque las zonas se derivan de `subs`, no de las keys de `demand`).
   No se toca ese bug en este entregable — queda anotado, no en scope.
7. **Referencia**: `reference_zone` = primera subárea (o parámetro
   explícito), igual que hoy.

Escribe además `topology/network_summary.json` (sidecar, vía `storage`)
con el resumen de fusión intra-zona del punto 4 — **no** es parte del
`NodalNetwork` que valida el schema ni lo consume el motor; es solo
trazabilidad/auditoría de cuánta capacidad de transmisión quedó "dentro"
de cada zona agregada.

### 3.5 `cli.py`

```
uv run gridforge scrape-topology --date 2026-08-01 --scope subarea \
    --demand-source ddem|pron --demand-split capacity|uniform \
    --out topology/network.json [--refresh]
```

`--scope` default `subarea`. Si se pasa `node`, usa el `build_network`
actual sin cambios (comportamiento actual preservado, incluyendo su bug
conocido). `area` levanta `NotImplementedError` con mensaje explícito.

## 4. Testing

- **`test_topology_parse.py`**: fixture GeoJSON mínimo (3-4 features,
  incluyendo un caso intra-subárea y uno inter-subárea) para
  `parse_map_lines` → valida extracción de `sub1`/`sub2`/rating/kv sin
  split de texto.
- **`test_topology_build.py`**: fixture con subestaciones de 2 subáreas,
  líneas map (inter + intra) y líneas `getAll` de relleno (incluyendo un
  caso de un-extremo-sin-match) → `build_subarea_network` produce
  `NodalNetwork` válido: 2 zonas, 1 branch inter-zona con rating/reactancia
  combinados correctamente, resumen intra-zona con el rating fusionado
  esperado.
- **`test_topology_golden.py`**: agregar golden fixture a nivel subárea
  (nuevo archivo bajo `tests/fixtures/topology/`, no modifica el golden
  de `node` existente) — corrida completa `parse → build_subarea_network`
  sobre datos reales congelados, valida contra red esperada serializada.
- **Live smoke** (marcado `live`, excluido por defecto): `--scope subarea`
  contra datos reales del día, assert `NodalNetwork` valida limpio y
  cuenta de zonas == 21 (o el subconjunto doméstico presente ese día).

## 5. Riesgos / decisiones explícitas

- **Reactancia en `getLines`**: confirmado que el payload no la trae;
  se cruza por `name` exacto contra `Line/getAll` (100% de cobertura
  verificada en vivo, ver §3.3). Sin riesgo residual — no se deja como
  decisión pendiente.
- **`base_kv` de una `Zone` = subárea**: no tiene significado físico
  directo (una subárea mezcla niveles de tensión). Se documenta como
  valor nominal, no usado por el motor de despacho actual (confirmado:
  `Zone.base_kv` no aparece referenciado en el cálculo de LMP, solo en
  metadata) — si eso cambia en el futuro, revisar.
- **`node`/`area` scope quedan explícitamente fuera de este cambio.** No
  se toca `build_network` actual ni su bug de spec-deviation (dropear
  ramas colgantes con log) — se re-envuelve tal cual detrás de la
  interfaz nueva.
