# ARCHITECTURE.md — Cursodex Extractor

> **Versión:** 0.4.2 · **Taxonomía canónica CINE-F ampliada**
> Documento de referencia permanente para el repositorio `cursos`.  
> Cualquier cambio arquitectónico debe reflejarse aquí antes de implementarse.

---

## 1. Visión Global del Ecosistema Cursodex

Cursodex es un índice abierto e interoperable de cursos gratuitos en línea que enlaza a recursos externos sin alojarlos en el servidor propio. Para evitar sobreingeniería y código difícil de mantener, el ecosistema completo se divide en cuatro capas desacopladas:

```
┌─────────────────────────────────────────────────────────────┐
│  1. Este repositorio (Python CLI — cursodex-extractor)      │
│     • Extracción, normalización, exportación (CSV / JSON-LD)│
│     • Sin estado (stateless) · Sin DB local · Sin servidor  │
│     • Ejecutado en runner desacoplado (GHA / contenedor SSH)│
└──────────────────────────┬──────────────────────────────────┘
                           │ stdout → JSON-LD array
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  2. Orquestador (n8n Community Edition)                     │
│     • Lanza el CLI de forma desacoplada (SSH / GHA / local) │
│     • Descarga el catálogo existente en lotes (GET /items)  │
│     • Compara canonical_url + urn:cursodex:sha256:<hash>    │
│     • Altas (POST) o actualizaciones seguras (Read-Merge-PUT│
│     • Lee y descarta el bloque _cursodex_meta antes del POST│
└──────────────────────────┬──────────────────────────────────┘
                           │ REST API (JSON-LD Omeka S v4+)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  3. Repositorio y Bandeja de Curaduría (Omeka S)            │
│     • Única fuente de verdad en producción (cursodex.com)   │
│     • Cursos nuevos entran como o:is_public = false         │
│     • Curaduría en lote con Bulk Edit, Bulk Import, Thesaurus│
│     • OAI-PMH Repository (oai_dc) para cosechadores         │
└─────────────────────────────────────────────────────────────┘
                           │ API pública de Omeka S
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  4. Generador de rutas formativas (Fase futura)             │
│     • Python + IA leyendo la API pública de Omeka S         │
│     • Modelado secuencial (de básico a experto)             │
└─────────────────────────────────────────────────────────────┘
```

**Implicación crítica:** Este repositorio **NO** debe contener servidores web, interfaces gráficas, bases de datos locales (SQLite / PostgreSQL) ni clientes HTTP hacia Omeka S. Es una herramienta CLI Unix ligera, predecible e interconectable.

---

## 2. Estructura de Directorios

```
cursos/
├── cli.py                   # Punto de entrada único (typer)
├── config.py                # Variables de entorno y constantes
├── pyproject.toml           # Dependencias y metadatos (gestionado con uv)
├── uv.lock                  # Lock file — commiteado para builds reproducibles
├── ARCHITECTURE.md          # Este documento
├── README.md
├── PLAN.md                  # Hoja de ruta del proyecto
├── AGENTS.md                # Guardrails e instrucciones de trabajo
├── .agent/rules/cursodex.md # Guardrails permanentes del repositorio
├── .github/copilot-instructions.md
│
│
├── core/
│   ├── crawler.py           # Clase Crawler (httpx + Playwright) y crawl_site() BFS
│   ├── extractor.py         # Integración extruct (JSON-LD, Microdata, OpenGraph, RDFa)
│   ├── parser.py            # Orquestador: extruct primario + bs4 fallback
│   └── exceptions.py        # NetworkError, ParsingError, ScraperException
│
├── providers/
│   ├── base.py              # ProviderBase ABC + registro automático
│   ├── ms_learn.py          # Microsoft Learn (API REST - learningPaths)
│   ├── openlearn.py         # OpenLearn (sitemap XML comprimido + extruct/DOM)
│   ├── aprende.py           # Aprende.org / Capacítate (API privada JSON)
│   ├── netacad.py           # Cisco NetAcad (Playwright + extruct)
│   └── __init__.py          # Auto-discovery + get_provider_for_url()
│
├── schemas/
│   ├── models.py            # Modelo Course Pydantic v2 estático (NO rdflib)
│   └── __init__.py
│
├── mappings/
│   └── vocab_map.yml        # 17 categorías CINE-F/JRC + niveles + idiomas
│
├── exporters/
│   ├── base.py              # BaseExporter ABC
│   ├── csv_exporter.py      # CSV compatible con Omeka S Bulk Import
│   ├── jsonld_exporter.py   # JSON-LD compatible con Omeka S REST API v4+
│   └── __init__.py
│
├── utils/
│   ├── logger.py            # Logger 100% a stderr; sin escritura a disco
│   └── __init__.py
│
├── tests/
│   ├── test_exporters_and_cli.py
│   ├── test_extractor_and_crawler.py
│   ├── test_models.py
│   └── test_providers.py
│
├── docs/
│   ├── TAXONOMY.md          # Manual normativo y semántico de las 17 categorías
│   ├── USER_GUIDE.md        # Guía de usuario y operación
│   └── index.html           # Manual visual autocontenido
│
└── legacy/                  # Scripts obsoletos (en .gitignore — no se publican en Git)
```

---

## 3. Contrato Unix: stdout / stderr

| Canal | Contenido | Nunca |
|-------|-----------|-------|
| `stdout` | Datos estructurados limpios: JSON-LD array cuando `--output -` (o CSV si `--format csv`) | Logs, warnings, mensajes de progreso, help text |
| `stderr` | 100% de logs (`INFO`, `WARNING`, `ERROR`) + resumen estructurado de ejecución | Datos estructurados del catálogo |

**Regla absoluta:** Prohibido usar `print()` para mensajes informativos en `cli.py`, `core/`, `providers/`, `exporters/` o `schemas/`. Toda salida informativa pasa por `utils/logger.py` → `sys.stderr`. Cuando se invoque help o errores de validación CLI, emitir a `stderr`.

### Formato del resumen de ejecución (stderr, al finalizar)

```json
{
  "event": "run_summary",
  "provider": "MicrosoftLearn",
  "url": "https://learn.microsoft.com/api/catalog/?locale=es-es",
  "courses_extracted": 42,
  "needs_review_count": 3,
  "exit_code": 0,
  "elapsed_seconds": 12.4,
  "timestamp": "2026-11-24T00:00:00Z"
}
```

---

## 4. Códigos de Salida Semánticos

| Código | Significado | Trigger en n8n |
|--------|-------------|----------------|
| `0` | Éxito — ≥ 1 cursos válidos extraídos | Procesar salida estructurada de stdout |
| `1` | Error crítico — excepción, error de red, argumento inválido | Alerta de fallo técnico |
| `2` | Éxito técnico — 0 cursos extraídos (posible cambio en DOM/API del proveedor) | Alerta temprana de regresión/rotura de scraper |

---

## 5. Contrato del Modelo `Course`

### 5.1 Campos del modelo Pydantic v2

| Campo Python | Alias / Mapeo exportación | Tipo | Requerido | Notas |
|---|---|---|---|---|
| `name` | `schema:name` / `dcterms:title` | `str` | ✅ | Nombre oficial del curso |
| `url` | URL cruda de origen | `str` | ✅ | URL capturada originalmente |
| `canonical_url` | `schema:url` / `dcterms:identifier` | `str` | ✅ | URL final canónica y deduplicable (calculada) |
| `content_hash` | `schema:identifier` (`urn:cursodex:sha256:...`) | `str` | ✅ | SHA-256 determinista (calculado) |
| `description` | `schema:description` / `dcterms:description` | `str \| None` | — | Máx ~350 chars, sin HTML, corte por oración/palabra |
| `provider` | `schema:provider` / `dcterms:publisher` | `str \| None` | — | Nombre del proveedor (ej. `Microsoft Learn`) |
| `authors` | `schema:author` / `dcterms:creator` | `list[str] \| None` | — | Autores/instructores (separados por `;` en CSV) |
| `category` | `schema:about` / `dcterms:subject` | `str \| None` | — | Categoría controlada de la taxonomía CINE-F 2013 + marcos JRC |
| `keywords` | `schema:keywords` | `list[str] \| None` | — | Etiquetas granulares originales del proveedor |
| `access_type` | `_cursodex_meta` + `schema:educationalCredentialAwarded` | `AccessType` (Enum) | — | 3 valores válidos (ver §5.2) |
| `educational_level` | `schema:educationalLevel` | `str \| None` | — | `Principiante`/`Intermedio`/`Avanzado` |
| `time_required` | `schema:timeRequired` | `str \| None` | — | ISO 8601 duración (`PT2H30M`) |
| `in_language` | `schema:inLanguage` / `dcterms:language` | `str \| None` | — | Código ISO 639-1 en minúsculas (`es`, `en`, `pt`) |
| `course_prerequisites` | `schema:coursePrerequisites` | `list[str] \| None` | — | Requisitos previos para secuenciación |
| `is_accessible_for_free` | `schema:isAccessibleForFree` | `bool` | ✅ | Siempre `True`. Si es `False`, se rechaza el registro |
| `image` | `schema:image` | `str \| None` | — | URL de imagen/portada (exportada como URI) |
| `last_seen_at` | `schema:dateModified` / `_cursodex_meta` | `datetime` | ✅ | Timestamp UTC de extracción |
| `needs_review` | `needs_review` (en `_cursodex_meta`) | `bool` | ✅ | Triaje automático de calidad |
| `review_notes` | `review_notes` (en `_cursodex_meta`) | `list[str]` | ✅ | Lista de motivos legibles de revisión |

### 5.2 Enum `AccessType` y Mapeo Pedagógico

| Valor Enum Python | Etiqueta oficial (`schema:educationalCredentialAwarded`) | Significado |
|---|---|---|
| `free_with_certificate` | `"Certificado gratuito"` | Curso gratuito con certificado o insignia verificable |
| `free_audit_paid_certificate` | `"Acceso gratuito (certificado de pago)"` | Acceso a contenidos gratuito; examen/certificado opcional de pago |
| `free_no_certificate` | `"Curso gratuito (sin certificado)"` | Acceso completamente gratuito sin credencial formal |

> [!CAUTION]
> Cualquier curso con coste de acceso obligatorio o bajo modalidad de prueba temporal ("7 días de prueba") debe descartarse con `ValueError` durante la validación del modelo.

### 5.3 Lógica de `canonical_url`

1. Esquema forzado a `https://`.
2. Dominio normalizado a minúsculas; ruta preservando mayúsculas y minúsculas.
3. Eliminación estricta de fragmentos (`#...`).
4. Eliminación de barra final redundante (`/`), excepto en el dominio raíz.
5. **Filtrado selectivo de parámetros de rastreo:** Elimina únicamente `utm_*`, `fbclid`, `gclid`, `mc_cid`, `mc_eid`, `ref`, `source`, `_hsenc`, `_hsmi`, `mkt_tok`.
6. **Preservación y ordenación de query parameters legítimos:** Parámetros funcionales (ej. `course_id=42&lang=es`) se conservan intactos y se ordenan alfabéticamente por clave.
7. **Trampa de redirección a portada (ELIXIR TeSS):** Si la URL resultante carece de ruta de recurso (es decir, es la raíz `https://dominio.com` o `https://dominio.com/`), se lanza `ValueError` para evitar registrar páginas de inicio de proveedores que redireccionan cursos retirados.

### 5.4 Lógica de `content_hash`

Calculado como SHA-256 sobre un JSON compacto (separadores `(",", ":")`) con `sort_keys=True` que contiene los campos descriptivos y pedagógicos normalizados:
```
access_type, authors (lista ordenada), category, course_prerequisites (lista ordenada),
description, educational_level, in_language, keywords (lista ordenada),
name, provider, time_required
```

**Excluidos explícitamente:** `last_seen_at`, `needs_review`, `review_notes`, `image`, `url`, `canonical_url`.

### 5.5 Activación automática de `needs_review`

`needs_review = True` se activa automáticamente si y solo si:
- `description` es `None` o contiene menos de 30 caracteres.
- `in_language` es `None`.
- `category == "Pendiente_Categoria"`.
- Se proporcionó un texto de duración no vacío que no pudo interpretarse como ISO 8601.

*(Nota: La ausencia de `educational_level` no activa `needs_review`, ya que muchos proveedores rigurosos no declaran nivel formal y esto evitará fatiga de revisión manual).*

### 5.6 Taxonomía normativa de 17 categorías

`mappings/vocab_map.yml` declara exactamente las siguientes etiquetas canónicas. El orden de esta tabla es el orden normativo de presentación; la resolución léxica selecciona la coincidencia más larga y usa el orden de vocabulario para desempatar. `Pendiente_Categoria` es un centinela interno y no pertenece a la taxonomía.

| # | Código UNESCO CINE-F 2013 | Etiqueta canónica | Marco complementario |
|---:|---|---|---|
| 1 | `0613` | Ciencia de Datos e Inteligencia Artificial | DigComp 2.2 |
| 2 | `0612` | Redes, Cloud y Ciberseguridad | DigComp 2.2 |
| 3 | `0613` | Programación y Desarrollo de Software | DigComp 2.2 |
| 4 | `0414` | Marketing Digital y Comercio Electrónico | DigComp 2.2 · EntreComp |
| 5 | `0011` | Competencias Digitales y Ofimática | DigComp 2.2 · DigCompEdu |
| 6 | `061` | Tecnologías de la Información y la Comunicación (General) | DigComp 2.2 |
| 7 | `04` | Administración de Empresas y Derecho | EntreComp |
| 8 | `07` | Ingeniería, Industria y Construcción | — |
| 9 | `05` | Ciencias Naturales, Matemáticas y Estadística | — |
| 10 | `08` + `052` | Sostenibilidad, Medio Ambiente y Agroalimentación | GreenComp |
| 11 | `09` | Salud y Bienestar | — |
| 12 | `01` | Educación y Pedagogía | DigCompEdu |
| 13 | `021` + `022` + `0232` | Artes, Diseño y Humanidades | Artes, Humanidades, Filología, Literatura y Lingüística |
| 14 | `03` | Ciencias Sociales, Periodismo e Información | — |
| 15 | `0231` | Idiomas | Adquisición de lenguas extranjeras · MCER |
| 16 | `0031` | Desarrollo Personal y Habilidades Transversales | LifeComp |
| 17 | `101`–`104` | Hostelería, Turismo y Servicios | — |

La separación lingüística es intencional: **#13** reúne las áreas CINE-F `021` (artes), `022` (humanidades) y `0232` (filología, literatura y lingüística); **#15** cubre `0231`, es decir, el aprendizaje y adquisición de idiomas conforme a niveles MCER. Los gentilicios de idioma no deben desviar títulos que contengan una señal filológica o literaria explícita.

Los marcos europeos JRC aportan vocabulario transversal y no sustituyen los códigos CINE-F: DigComp 2.2 para competencias digitales, DigCompEdu para competencia digital docente, EntreComp para emprendimiento, LifeComp para competencias personales y sociales, y GreenComp para sostenibilidad.

El inventario completo de sinónimos vigentes, reglas de desambiguación y contrato de datos para rutas formativas se mantiene en [docs/TAXONOMY.md](docs/TAXONOMY.md).

---

## 6. Contrato de Exportación

### 6.1 JSON-LD — Estructura compatible con Omeka S REST API v4+

En la API REST de Omeka S v4+:
- Cada elemento dentro de un array de propiedad **debe incluir `"property_id": "auto"`**.
- Textos literales: `{"type": "literal", "property_id": "auto", "@value": "..."}`.
- URLs y URIs: `{"type": "uri", "property_id": "auto", "@id": "..."}`.
- Propiedades privadas de auditoría: se almacena el hash y la fecha con `"is_public": false`.
- **NO incluir `"o:id"`** dentro de `"@type"` ni `"o:resource_class"`.
- **Regla anti-polución de categorías:** Si `category == "Pendiente_Categoria"`, **se omiten** las propiedades públicas `schema:about` y `dcterms:subject` en el grafo RDF público (evitando ensuciar las facetas de Omeka S y OAI-PMH). El valor se conserva íntegramente en el bloque privado `_cursodex_meta["category"]` y en `review_notes`.

```json
[
  {
    "@type": ["o:Item", "schema:Course"],
    "o:is_public": false,

    "schema:name": [
      {"type": "literal", "property_id": "auto", "@value": "Introducción a Python", "@language": "es"}
    ],
    "schema:url": [
      {"type": "uri", "property_id": "auto", "@id": "https://proveedor.com/cursos/python"}
    ],
    "schema:description": [
      {"type": "literal", "property_id": "auto", "@value": "Aprende los fundamentos de Python...", "@language": "es"}
    ],
    "schema:provider": [
      {"type": "literal", "property_id": "auto", "@value": "Microsoft Learn"}
    ],
    "schema:author": [
      {"type": "literal", "property_id": "auto", "@value": "Jane Doe"}
    ],
    "schema:about": [
      {"type": "literal", "property_id": "auto", "@value": "Programación y Desarrollo de Software"}
    ],
    "schema:keywords": [
      {"type": "literal", "property_id": "auto", "@value": "Python"},
      {"type": "literal", "property_id": "auto", "@value": "Backend"}
    ],
    "schema:timeRequired": [
      {"type": "literal", "property_id": "auto", "@value": "PT4H30M"}
    ],
    "schema:educationalLevel": [
      {"type": "literal", "property_id": "auto", "@value": "Principiante"}
    ],
    "schema:inLanguage": [
      {"type": "literal", "property_id": "auto", "@value": "es"}
    ],
    "schema:isAccessibleForFree": [
      {"type": "literal", "property_id": "auto", "@value": "true"}
    ],
    "schema:educationalCredentialAwarded": [
      {"type": "literal", "property_id": "auto", "@value": "Certificado gratuito"}
    ],
    "schema:coursePrerequisites": [
      {"type": "literal", "property_id": "auto", "@value": "Conocimientos básicos de computación"}
    ],
    "schema:image": [
      {"type": "uri", "property_id": "auto", "@id": "https://proveedor.com/img/python.jpg"}
    ],
    "schema:identifier": [
      {"type": "literal", "property_id": "auto", "@value": "urn:cursodex:sha256:a3f4b2c1...", "is_public": false}
    ],
    "schema:dateModified": [
      {"type": "literal", "property_id": "auto", "@value": "2026-11-24T00:00:00Z", "is_public": false}
    ],

    "dcterms:title": [
      {"type": "literal", "property_id": "auto", "@value": "Introducción a Python"}
    ],
    "dcterms:identifier": [
      {"type": "literal", "property_id": "auto", "@value": "https://proveedor.com/cursos/python"}
    ],
    "dcterms:description": [
      {"type": "literal", "property_id": "auto", "@value": "Aprende los fundamentos de Python..."}
    ],
    "dcterms:publisher": [
      {"type": "literal", "property_id": "auto", "@value": "Microsoft Learn"}
    ],
    "dcterms:creator": [
      {"type": "literal", "property_id": "auto", "@value": "Jane Doe"}
    ],
    "dcterms:language": [
      {"type": "literal", "property_id": "auto", "@value": "es"}
    ],
    "dcterms:subject": [
      {"type": "literal", "property_id": "auto", "@value": "Programación y Desarrollo de Software"}
    ],

    "_cursodex_meta": {
      "canonical_url": "https://proveedor.com/cursos/python",
      "content_hash": "a3f4b2c1...",
      "category": "Programación y Desarrollo de Software",
      "access_type": "free_with_certificate",
      "last_seen_at": "2026-11-24T00:00:00Z",
      "needs_review": false,
      "review_notes": []
    }
  }
]
```

### 6.2 CSV — Estructura compatible con Omeka S Bulk Import

- Codificación: `utf-8` estándar sin BOM (el BOM rompe tuberías stdout y corrompe la primera columna en `fgetcsv`).
- Separador de columnas: `,` (coma).
- Separador de valores múltiples dentro de celdas: `;` (punto y coma). Los puntos y comas internos dentro de los elementos se sustituyen por comas antes de concatenar.
- Si `category == "Pendiente_Categoria"`, las celdas `schema:about` y `dcterms:subject` se dejan vacías.
- Cabeceras directas en formato `namespace:property`:

```
dcterms:title,dcterms:identifier,dcterms:publisher,dcterms:creator,dcterms:description,dcterms:language,dcterms:subject,schema:name,schema:url,schema:description,schema:provider,schema:author,schema:about,schema:keywords,schema:timeRequired,schema:educationalLevel,schema:inLanguage,schema:isAccessibleForFree,schema:educationalCredentialAwarded,schema:coursePrerequisites,schema:image,canonical_url,content_hash,access_type,needs_review,review_notes,last_seen_at
```

---

## 7. Configuración del Cliente HTTP

```python
# config.py — valores por defecto (sobreescribibles por variables de entorno)
USER_AGENT       = "CursodexBot/1.0 (+https://cursodex.com; academic research index)"
HTTP_TIMEOUT     = 30          # segundos
COURTESY_DELAY   = 1.0         # segundos entre peticiones
FOLLOW_REDIRECTS = True
MAX_RESULTS      = 0           # variable declarada; el CLI limita ejecuciones con --limit
```

---

## 8. Proveedores Activos (v1.0)

| # | Provider | Módulo | Estrategia | URL de entrada | `access_type` por defecto |
|---|---|---|---|---|---|
| 1 | **Microsoft Learn** | `ms_learn.py` | API REST JSON (`learningPaths`; módulos opt-in) | `https://learn.microsoft.com/api/catalog/?locale=es-es` | `free_with_certificate` |
| 2 | **OpenLearn (The Open University)** | `openlearn.py` | Sitemap `.xml.gz`, `extruct` y fallback OpenGraph/DOM | `https://www.open.edu/openlearn/free-courses/full-catalogue` | Evidencia HTML de credencial; si no, `free_no_certificate` |
| 3 | **Aprende.org** | `aprende.py` | API JSON pública con detalle perezoso | `https://aprende.org/cursos` | `free_with_certificate` |
| 4 | **Cisco NetAcad** | `netacad.py` | Playwright SPA; tarjetas filtradas por precio explícito | `https://www.netacad.com/courses/all-courses` | Insignia/certificado explícito; en otro caso `free_no_certificate` |

### 8.1 Notas específicas por proveedor

**Microsoft Learn (`ms_learn.py`):**
- La API devuelve colecciones separadas: `learningPaths`, `modules`, `courses`.
- Extraer exclusivamente **`learningPaths`** por defecto (itinerarios completos de varias horas). Los `modules` se extraen solo con flag `--enable-modules`.
- Campos de API: `duration_in_minutes` (con fallback defensivo a `durationInMinutes`), `levels[]`, `products[]`, `roles[]`.

**OpenLearn (`openlearn.py`):**
- Intenta el sitemap de cursos comprimido y usa la paginación del catálogo como respaldo.
- Las fichas probadas no exponen necesariamente `schema:Course`; se combina OpenGraph con DOM para nivel, duración, tema e idioma.
- Solo se declara credencial gratuita cuando la ficha menciona explícitamente una *Free statement of participation* o *free digital badge*.
- Si HTTP devuelve 403 o el sitemap contiene un desafío Cloudflare, se detiene y reporta el bloqueo; no automatiza la evasión del WAF. Un 503 permite probar las alternativas HTTP documentadas.

**Aprende.org (`aprende.py`):**
- Usa `Crawler` y acepta la lista raíz vigente o contenedores `courses`, `data` e `items`; consulta detalles solo para cursos que se van a emitir con descripción ausente o menor de 20 caracteres. Un detalle sin descripción suficiente se conserva honestamente y queda sujeto a revisión.

**Cisco NetAcad (`netacad.py`):**
- Renderiza por defecto el catálogo SPA, descarta tarjetas sin precio gratuito explícito y no consulta endpoints bloqueados de detalle.

**Proveedor retirado — HubSpot Academy:**
- `providers/hubspot.py` se trasladó a `legacy/` y queda fuera de Git. El sondeo confirmó que el sitemap ya no publica rutas `/courses/` y que la página española servía una shell SPA sin datos de curso aprovechables en estático.

---

## 9. Crawler BFS Genérico

El crawler BFS (`core/crawler.py::crawl_site`) está **desactivado por defecto**.
- Se activa únicamente con `--enable-bfs`.
- Si se pasa una URL sin adaptador conocido y sin `--enable-bfs`, el CLI emite error en `stderr` y finaliza con código `1`.

---

## 10. Gestión de Dependencias con `uv`

```bash
uv add <paquete>
uv add --dev <paquete>
uv sync --frozen --link-mode=copy
uv run cursodex run --provider ms_learn --limit 5 --output -
uv run pytest -v
uv run ruff check .
```

---

## 11. Contrato de Integración con n8n

Dado el aislamiento de contenedores Docker en Webmin/VPS (donde el contenedor Alpine de n8n carece de Python o Playwright), n8n ejecuta este CLI de manera desacoplada:
1. Mediante SSH a un contenedor worker o host.
2. O disparando un workflow de GitHub Actions que corre el CLI y envía el JSON resultante.

### Flujo de Sincronización en n8n:
1. `n8n` descarga en lotes el catálogo existente de Omeka S (`GET /api/items?per_page=100&resource_class_id=...`).
2. Mapea en memoria un índice clave: `canonical_url` → `{item_id, content_hash}` (leyendo `urn:cursodex:sha256:...` de `schema:identifier`).
3. Para cada curso emitido en `stdout`:
   - Si `canonical_url` no existe en Omeka S → **POST /api/items** (creación).
   - Si `canonical_url` existe y `content_hash` es idéntico → **Skip** (sin cambios).
   - Si `canonical_url` existe pero `content_hash` difiere → **Read-Merge-PUT /api/items/:id** (obtiene el ítem actual, actualiza propiedades modificadas y envía `PUT` completo; **nunca `PATCH`**, para no borrar campos previos ni ediciones del curador).

---

## 12. Referentes Arquitectónicos y Aprendizajes de Terceros

Las decisiones de diseño de Cursodex integran lecciones de los principales agregadores educativos abiertos:

1. **OERSI (`oersi-etl`) y Perfil AMB (`dini-ag-kim/amb`):**
   - *Separación estricta entre facetas y etiquetas:* `schema:about` (`category`) provee una categoría controlada única y normalizada para navegación temática; `schema:keywords` retiene las etiquetas libres del proveedor para el futuro recomendador de rutas con IA.
   - *Hibridación CINE-F 2013 + marcos europeos JRC:* Las 17 categorías cubren los bloques CINE-F `00`–`10` con especialización digital, sostenibilidad y la separación lingüística `0231`/`0232`; DigComp 2.2, DigCompEdu, EntreComp, LifeComp y GreenComp aportan vocabulario transversal.

2. **MOOChub (`schema:Course` interoperable):**
   - Estandarización de duraciones a ISO 8601 (`PT2H30M`), distinción explícita de credencial en `schema:educationalCredentialAwarded` e indexación de la ficha canónica permanente del curso, evitando duplicidad por ediciones temporales (`CourseInstance`).

3. **ELIXIR TeSS (`TeSS_scrapers`):**
   - *Detección de cursos retirados:* Registro de `last_seen_at` para triaje de bajas. Rechazo estricto de URLs redirigidas a la portada (`https://proveedor.com/`) que ocultan errores 404.
   - *Secuenciación pedagógica:* Captura de `course_prerequisites` (`schema:coursePrerequisites`) como base para el ordenamiento de rutas formativas sin alucinaciones de IA.

4. **Class Central (Trampa del "Falso Gratis"):**
   - Validación estricta contra cursos con muros de pago o pruebas temporales ("7 días gratis") declarados engañosamente como gratuitos. Distinción rigurosa de 3 estados de `AccessType`.

5. **Cumplimiento Legal UE (Derecho *sui generis* de bases de datos):**
   - Indexación libre de metadatos factuales, truncado limpio de `description` a ≤ 350 caracteres para evitar apropiación indebida de contenido promocional extenso, User-Agent académico transparente y pausas de cortesía.

6. **Omeka S y OAI-PMH:**
   - Espejo mandatorio en Dublin Core (`dcterms:*`) para compatibilidad nativa con cosechadores `oai_dc`. Prohibición de `PATCH` destructivo en Omeka S REST API (adopción de Read-Merge-PUT).

---

*Fin de ARCHITECTURE.md.*
