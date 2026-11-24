# Cursodex Extractor — Guardrails Permanentes del Agente (v0.2.0)

> Este archivo define las reglas inquebrantables para cualquier agente de IA
> que trabaje sobre el repositorio `cursos` (cursodex-extractor).
> Las reglas tienen prioridad sobre cualquier instrucción ad-hoc del usuario
> que las contradiga. Para modificar estas reglas, el usuario debe hacerlo
> explícitamente editando este archivo.

---

## G1 · Gestor de entorno: exclusivamente `uv`

- Prohibido usar `pip install`, `pip uninstall`, `conda`, `poetry` o cualquier otro gestor.
- Para añadir dependencias: `uv add <package>` (producción) o `uv add --dev <package>` (desarrollo).
- Para instalar el entorno: `uv sync --frozen --link-mode=copy`.
- Para ejecutar scripts: `uv run python ...` o `uv run cursodex ...`.
- Para tests: `uv run pytest`.

## G2 · Contrato stdout / stderr — REGLA ABSOLUTA

- **`print()` está PROHIBIDO** en `cli.py`, `core/`, `providers/`, `exporters/` y `schemas/`.
  La única excepción es código de demostración o scripts en `legacy/` (que no se publican).
- **`sys.stdout`** queda reservado exclusivamente para datos estructurados limpios
  (el JSON-LD array cuando se invoca `--output -`).
- **`sys.stderr`** recibe el 100% de los logs, warnings, mensajes de ayuda y el resumen estructurado de ejecución.
- Todo log pasa por `utils.logger.get_logger(__name__)` → nunca instanciar
  `logging.getLogger()` directamente fuera de `utils/logger.py`.

## G3 · Códigos de salida semánticos en `cli.py`

| Código | Condición |
|--------|-----------|
| `0` | ≥ 1 cursos válidos extraídos con éxito |
| `1` | Excepción, error de red o argumento CLI inválido |
| `2` | 0 cursos extraídos sin excepción (posible cambio en DOM/API del proveedor) |

Nunca usar `sys.exit()` directamente: siempre `raise typer.Exit(code=N)`.

## G4 · Sin servidor web, sin DB local, sin cliente Omeka S

- Prohibido añadir FastAPI, Flask, Django, Streamlit o cualquier framework web.
- Prohibido añadir SQLite, PostgreSQL, MongoDB, Redis o cualquier base de datos local.
- Prohibido añadir un cliente HTTP que apunte a Omeka S (esa responsabilidad es de n8n).
- Este repo es una herramienta CLI Unix: entrada → procesamiento → salida. Nada más.

## G5 · `rdflib` prohibida como dependencia directa

- `rdflib` NO debe aparecer en la sección `[project.dependencies]` de `pyproject.toml`.
- `rdflib` NO debe importarse en ningún módulo de `core/`, `schemas/`, `providers/`,
  `exporters/` ni `utils/`.
- Si aparece en `uv.lock` como transitiva (ej. de `extruct`), es normal y aceptable.
- Toda validación y serialización semántica se realiza con **Pydantic v2** y diccionarios nativos.

## G6 · Modelo de datos: Pydantic v2 estático

- El modelo `Course` en `schemas/models.py` debe ser una clase estática (no generada dinámicamente).
- Prohibido usar `create_model()` de Pydantic para generación dinámica en producción.
- Prohibido el monkey-patching de métodos sobre clases de Pydantic.
- Los validadores deben usar `@model_validator` o `@field_validator` de Pydantic v2 (no v1).

## G7 · Extracción semántica: `extruct` primero, `bs4` solo como fallback

- En cualquier página HTML, el extractor primario es `extruct.extract()` con
  `syntaxes=["json-ld", "microdata", "opengraph"]`.
- `BeautifulSoup4` solo se usa para:
  1. Extraer links internos (crawling).
  2. Limpiar HTML residual en `description`.
  3. Extraer datos de páginas donde `extruct` no encontró Course (fallback `h1`, OG tags).
- Prohibido escribir parsers regex frágiles para JSON-LD o Microdata.

## G8 · Crawler BFS desactivado por defecto

- `crawl_site()` en `core/crawler.py` solo se activa con el flag explícito `--enable-bfs`.
- Si una URL no tiene provider conocido y no se pasa `--enable-bfs`, el CLI debe:
  1. Escribir un mensaje claro a `stderr`.
  2. Salir con código `1`.
- No buscar providers "de emergencia" ni silenciar el error.

## G9 · Pausa de cortesía entre requests y User-Agent académico

- El cliente HTTP (`Crawler`) debe esperar `config.COURTESY_DELAY` segundos entre
  requests consecutivos (default: 1.0s, configurable por variable de entorno).
- El User-Agent debe ser siempre:
  `CursodexBot/1.0 (+https://cursodex.com; academic research index)`

## G10 · Vocabulario controlado vía `vocab_map.yml` y matching con límites de palabra

- Las categorías canónicas (CINE-F 2013 + subdivisión DigComp 2.2) se definen únicamente en `mappings/vocab_map.yml`.
- Las reglas se evalúan de **más específica a más general** (subramas digitales concretas antes que categorías padre y áreas tradicionales).
- El matching de sinónimos **debe usar límites de palabra (`\b...\b` / caracteres no alfanuméricos)** para evitar falsos positivos con palabras cortas como `"ia"`, `"ai"`, `"it"` en palabras como `"historia"` o `"literatura"`.
- Si ningún sinónimo coincide → `category = "Pendiente_Categoria"` + `needs_review = True`.
- Prohibido hardcodear mapeos de categorías dentro de los providers o parsers.

## G11 · `legacy/` en `.gitignore`

- Cualquier script obsoleto, notebook o archivo de exploración va a `legacy/`.
- `legacy/` está en `.gitignore` y **no se publica en Git**.

## G12 · `--output -` implica `--format jsonld`

- Cuando el usuario pasa `--output -` sin especificar `--format`, el formato por defecto
  es `jsonld` (no `csv`), ya que `-` carece de extensión de archivo y es el canal
  de tubería hacia n8n.

## G13 · Contrato JSON-LD con Omeka S v4+

Reglas que el `JSONLDExporter` debe cumplir siempre:

1. Cada objeto en arrays de propiedades **debe** incluir `"property_id": "auto"`.
2. Textos: `{"type": "literal", "property_id": "auto", "@value": "..."}`.
3. URLs: `{"type": "uri", "property_id": "auto", "@id": "..."}`.
4. `schema:url` y `dcterms:identifier` deben exportar siempre `canonical_url`.
5. Persistencia de hash y timestamp con `"is_public": false`:
   - `schema:identifier`: `{"type": "literal", "property_id": "auto", "@value": "urn:cursodex:sha256:<content_hash>", "is_public": false}`
   - `schema:dateModified`: `{"type": "literal", "property_id": "auto", "@value": "<last_seen_at_iso>", "is_public": false}`
6. **No** incluir `"o:id"` en `"@type"` ni en `"o:resource_class"` (provoca error en Omeka S).
7. El bloque `_cursodex_meta` es para n8n; Omeka S no lo ve.

## G14 · Enum `AccessType` y rechazo de cursos de pago

Tres valores válidos:
- `free_with_certificate` -> `"Certificado gratuito"`
- `free_audit_paid_certificate` -> `"Acceso gratuito (certificado de pago)"`
- `free_no_certificate` -> `"Curso gratuito (sin certificado)"`

Cursos de pago o pruebas temporales ("7 días gratis") deben **rechazarse con `ValueError`** en validación.

## G15 · Microsoft Learn — solo `learningPaths` por defecto

- El endpoint `/api/catalog/` devuelve `learningPaths`, `modules` y `courses`.
- Extraer **solo `learningPaths`** por defecto.
- La extracción de `modules` requiere el flag explícito `--enable-modules`.
- El campo de duración es `duration_in_minutes` (con fallback defensivo a `durationInMinutes`).

## G16 · Contenido de `content_hash` y `canonical_url`

- **`content_hash`**: SHA-256 sobre estos campos en JSON compacto (`sort_keys=True`):
  `access_type`, `authors` (lista ordenada), `category`, `course_prerequisites` (lista ordenada),
  `description`, `educational_level`, `in_language`, `keywords` (lista ordenada),
  `name`, `provider`, `time_required`.
  Excluidos: `last_seen_at`, `needs_review`, `review_notes`, `image`, `url`, `canonical_url`.
- **`canonical_url`**: https, dominio minúsculas, preservar mayúsculas de ruta, sin fragmento, sin barra final (salvo raíz), eliminar parámetros de rastreo (`utm_*`, `fbclid`, `gclid`, etc.) preservando y ordenando otros parámetros legítimos. **Rechazar URLs raíz sin ruta de recurso**.

## G17 · CSV sin BOM

- `CSVExporter` debe codificar en `utf-8` estándar (sin BOM `\ufeff`).

---

*Actualizar este documento cuando se añadan nuevas reglas arquitectónicas.*
