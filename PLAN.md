# PLAN.md — Hoja de Ruta Maestra End-to-End: Cursodex (TFM)

**Documento de Gobernanza y Plan Maestro de Implementación**  
**Proyecto:** Cursodex — Repositorio Semántico e Índice de Cursos Gratuitos en Línea  
**Versión:** 1.1.0 (Pasos 4A–4C completados)
**Fecha de corte:** Noviembre 2026 | **Hito Final:** 30 de abril de 2027  
**Referencias normativas:** [ARCHITECTURE.md](file:///c:/Users/Eddie%20Barillas/OneDrive%20-%20Veeva%20Systems,%20Inc/Documents/GitHub/cursos/ARCHITECTURE.md), [.agent/rules/cursodex.md](file:///c:/Users/Eddie%20Barillas/OneDrive%20-%20Veeva%20Systems,%20Inc/Documents/GitHub/cursos/.agent/rules/cursodex.md)

---

## 1. Contexto Global y Filosofía Arquitectónica del Sistema

Cursodex es un catálogo académico abierto, semántico e interoperable que agrega, normaliza y expone cursos gratuitos en línea sin alojar el contenido educativo en servidores propios. Para maximizar la mantenibilidad, escalabilidad y rigor científico, el ecosistema se divide estrictamente en 3 capas desacopladas:

1. **Extractor CLI Stateless (`cursos` — este repositorio):** Motor ligero en Python sin base de datos local ni servidor web, gestionado con `uv`. Se invoca vía cron o webhook, procesa fuentes externas y emite registros limpios y validados hacia `stdout` (o archivo) en formatos duales (`JSON-LD` para Omeka S / `CSV` para importación masiva).
2. **Orquestador de Integración (`n8n` Community Edition):** Recibe o desencadena las ejecuciones del CLI, consulta el índice existente de Omeka S mediante su API REST v4+, detecta cambios basándose en `canonical_url` y `content_hash`, inyecta altas (`POST`) y actualizaciones seguras (**Read-Merge-PUT**) hacia la bandeja de curaduría de Omeka S.
3. **Repositorio Semántico y Bandeja de Curaduría (`Omeka S` en `cursodex.com/omekas/`):** Única fuente de la verdad en producción. Aloja los datos mapeados bajo estándares internacionales (`Schema.org` + `Dublin Core`), expone navegación por facetas (`Faceted Browse`), cosechado académico mediante `OAI-PMH` (`oai_dc`) y gestiona la moderación humana antes de publicar (`o:is_public: true`).

```
+---------------------------------------------------------------------------------------+
| FUENTES EXTERNAS (Microsoft Learn, OpenLearn, Aprende.org, Cisco NetAcad)              |
+---------------------------------------------------------------------------------------+
                                           |
                                           v
+---------------------------------------------------------------------------------------+
| 1. EXTRACTOR CLI STATELESS (Este Repositorio: cursos)                                 |
|    - httpx / Playwright + extruct + BeautifulSoup4                                    |
|    - Normalizador Pydantic v2 (schemas/models.py) + Vocabulario (vocab_map.yml)       |
|    - Exporters duales (JSON-LD con property_id:"auto" / CSV UTF-8 sin BOM)            |
|    - Salida limpia a stdout / logs y métricas estructuradas a stderr (exit codes 0/1/2) |
+---------------------------------------------------------------------------------------+
                                           |
                                           v  (JSON-LD / Exit Codes / run_summary)
+---------------------------------------------------------------------------------------+
| 2. ORQUESTADOR n8n (Docker en VPS o GitHub Actions Worker)                            |
|    - Change Detection: canonical_url + urn:cursodex:sha256:<content_hash>             |
|    - Altas con POST (o:is_public: false -> Bandeja de Curaduría)                      |
|    - Actualizaciones seguras: Read-Merge-PUT (GET full -> Merge -> PUT full)          |
|    - Control de tasa: Lotes de 5 ítems + pausa 300 ms                                 |
+---------------------------------------------------------------------------------------+
                                           |
                                           v  (REST API v4+ con Custom Auth)
+---------------------------------------------------------------------------------------+
| 3. REPOSITORIO SEMÁNTICO (Omeka S en cursodex.com/omekas/)                            |
|    - Ontologías nativas: Schema.org (schema:Course) + Dublin Core (espejo)            |
|    - Bandeja de Curaduría: Moderación y publicación masiva con Bulk Edit              |
|    - Portal Público: Faceted Browse + JSON-LD embebido + OAI-PMH (oai_dc)             |
|    - Generador de Rutas con IA (Hito 4): Agrupaciones temáticas (schema:ItemList)    |
+---------------------------------------------------------------------------------------+
```

---

## 2. Estado Actual Exacto del Repositorio (Snapshot Post-Paso 4C)

### 2.1 Componentes 100% Terminados y Verificados en Producción

El repositorio ha superado los **Pasos 1, 2, 3 y 4A–4C**, con validación de pruebas de sistema operativo, lint y tipado:

* **Gestión de Entorno y Gobernanza (`pyproject.toml`, `uv.lock`):**
  * Entorno totalmente gestionado por `uv` (`link-mode = "copy"`), con paquete instalable y versión de release `0.4.1`.
  * Dependencias fijadas y reproducibles para HTTP (`httpx`, `playwright`), extracción (`extruct`, `beautifulsoup4`, `lxml`, `lxml-html-clean`, `html5lib`), modelo (`pydantic`, `pyyaml`) y CLI (`typer`, `click`, `typing-extensions`).
  * Dependencias de desarrollo completas (`pytest`, `pytest-httpx`, `respx`, `ruff`, `mypy`).

* **Modelo Semántico Estático (`schemas/models.py`):**
  * Modelo Pydantic v2 estático con inmutabilidad de validación segura (`object.__setattr__`).
  * Canonización estricta de URLs (`canonicalize_url()`): forzado de esquema `https`, dominios en minúsculas, stripping de puertos por defecto (`:80` y `:443`), eliminación de parámetros de rastreo (`utm_*`, `fbclid`, etc.), preservación y ordenación de query params legítimos y trampa anti-redirección de portada (rechaza rutas raíz vacías).
  * Sanitización factual de textos y listas: `clean_text_field()` y `clean_and_dedup_list()` limpian entidades HTML (`html.unescape`), retiran etiquetas HTML y colapsan espacios en blanco en `name`, `provider`, `authors`, `keywords` y `course_prerequisites`.
  * Filtro anti-falsos gratis: rechaza inmediatamente cualquier curso con `is_accessible_for_free=False`.
  * Normalización temporal: duraciones a ISO 8601 (`PT4H30M`), soporte explícito para días (`"3 días"` -> `"P3D"`) y rechazo de duraciones negativas. Fechas en `last_seen_at` forzadas a `datetime.UTC`.
  * Validación e higienización de imágenes: resolución de rutas relativas con `urljoin()` contra `canonical_url` y descarte a `None` de esquemas inseguros o inválidos.
  * Determinismo de cambio (`content_hash` SHA-256): cubre todos los campos descriptivos y pedagógicos (`name`, `provider`, `authors`, `category`, `keywords`, `access_type`, `educational_level`, `time_required`, `in_language`, `description`, `course_prerequisites`) ordenando listas de forma insensible a mayúsculas (`key=str.lower`). Excluye explícitamente `last_seen_at`, `needs_review` y notas.
  * Idempotencia comprobada: `Course.model_validate(c.model_dump())` produce un modelo idéntico con el mismo hash.

* **Vocabulario Controlado Jerárquico (`mappings/vocab_map.yml`):**
  * Taxonomía de 17 categorías canónicas que cubre los bloques CINE-F 2013 `00`–`10`, incluida la separación de `0232` (Filología, Literatura y Lingüística) frente a `0231` (adquisición de idiomas).
  * Alineación complementaria con DigComp 2.2, DigCompEdu, EntreComp, LifeComp y GreenComp.
  * Resolución léxica por coincidencia más larga con límites de palabra (`match_synonym_boundary`); el orden del vocabulario desempata coincidencias igual de específicas.
  * Cobertura de sinónimos bilingües con límites estrictos de palabra (`match_synonym_boundary`), evitando falsos positivos con acrónimos cortos (`"ia"`, `"ai"`, `"it"`, `"ti"`, `"r"`, `"c"`).
  * Sinónimos específicos agregados para IoT, Cisco Packet Tracer, Power Platform, Power Apps, Ventas y Atención al Cliente.

* **Contrato de Exportación Dual (`exporters/`):**
  * `JSONLDExporter`: Genera estructura compatible con la API REST de Omeka S v4+. Inyecta `"property_id": "auto"` en cada nodo, `"o:is_public": false`, propiedades de auditoría privadas (`"is_public": false`), espejo Dublin Core para OAI-PMH (`dcterms:*`) y bloque privado `_cursodex_meta`.
  * **Regla anti-polución semántica:** Si `category == "Pendiente_Categoria"`, se omiten `schema:about` y `dcterms:subject` en el grafo público tanto en JSON-LD como en CSV para no ensuciar las facetas públicas ni OAI-PMH, preservándose en `_cursodex_meta["category"]`.
  * `CSVExporter`: Formato UTF-8 sin BOM con separador `;` para listas internas, con escape automático de puntos y comas internos a comas antes de concatenar.

* **Punto de Entrada CLI Unix (`cli.py`):**
  * Contrato Unix estricto: `stdout` exclusivo para datos estructurados limpios (`--output -`), `stderr` para 100% de logs, avisos y resumen estructurado `run_summary`.
  * Códigos de salida semánticos garantizados: `0` (>= 1 curso extraído con éxito), `2` (0 cursos extraídos sin error de red, para control en n8n), `1` (error de ejecución, de red o de sintaxis CLI).
  * Control de excepciones Click/Typer: captura `click.ClickException` para evitar la colisión nativa de código 2 de Click y anula el markup Rich (`rich_markup_mode=None`) para prevenir escapes ANSI en tuberías.
  * Invocación sin argumentos: emite mensaje a `stderr` con código 1 sin escribir en `stdout`.

* **Calidad y Tests:** Suite de modelos, proveedores, exportadores y subprocesos del CLI, con verificación de Ruff y mypy incluyendo `tests/`.

---

### 2.2 Cierre de los Pasos 4A, 4B y 4C

| Paso | Alcance | Estado |
|---|---|---|
| **4A** | Infraestructura `extruct`, parser semántico y ciclo de vida HTTP/Playwright | **Completado** |
| **4B** | Adaptador Microsoft Learn, base de proveedor y prueba de HubSpot | **Completado**; Microsoft Learn permanece activo |
| **4C** | OpenLearn, saneamiento de Aprende.org y NetAcad, cobertura offline y documentación | **Completado** |

El catálogo v1 queda limitado a cuatro proveedores operativos: `ms_learn`, `openlearn`, `aprende` y `netacad`. HubSpot Academy se movió a `legacy/` y está excluido del tracking: su sitemap ya no publicaba rutas `/courses/` y la shell SPA española no ofrecía metadatos de curso utilizables en estático.

---

## 3. Especificación Detallada del Paso 4 (Cierre del Hito 1 — Límite: 31/01/2027)

El Paso 4 completa los adaptadores de proveedores reales y la infraestructura semántica primaria de extracción. Los contratos de exportación y CLI se conservan; el vocabulario y la precedencia de categorías se ajustaron para la clasificación observada en Microsoft Learn.

### 3.1 `core/extractor.py` (Nuevo Módulo) y Refactor de `core/parser.py`

* **Extracción Semántica Primaria con `extruct`:**
  * Crear `core/extractor.py` encapsulando `extruct.extract(html, base_url=url, syntaxes=['json-ld', 'microdata', 'opengraph'])`.
  * La función principal `extract_course_candidates(html: str, base_url: str) -> list[dict]` debe priorizar:
    1. Bloques JSON-LD donde `@type` sea `"Course"` o contenga `"Course"` (incluyendo listas de grafos `@graph`).
    2. Microdata con `itemtype="http://schema.org/Course"`.
    3. OpenGraph como metadatos de apoyo (`og:title`, `og:description`, `og:image`).
* **Rol de `core/parser.py` (Fallback DOM y Normalización Ligera):**
  * `BeautifulSoup4` solo actuará si `extruct` no encuentra ningún descriptor `schema:Course`.
  * En ese caso, extraerá heurísticamente desde selectores semánticos (`h1`, `meta[name=description]`, párrafos principales) para armar un borrador de `Course` que necesariamente entrará con `needs_review: true`.

### 3.2 Mejoras Requeridas en `core/crawler.py`

1. **Reutilización del Navegador Playwright (Ciclo de Vida Único):**
   * Modificar `Crawler` para permitir abrir una sola instancia de Chromium al inicio de la corrida del proveedor y cerrarla al finalizar:
     ```python
     class DynamicBrowserContext:
         def __enter__(self):
             self.playwright = sync_playwright().start()
             self.browser = self.playwright.chromium.launch(headless=True)
             return self.browser
         def __exit__(self, exc_type, exc_val, exc_tb):
             self.browser.close()
             self.playwright.stop()
     ```
   * Evita abrir y cerrar un subproceso de navegador por cada URL raspada, reduciendo el consumo de CPU y acelerando los scrapers en un 80%.
2. **Filtrado de Extensiones no-HTML en Rastreo BFS:**
   * En `crawl_site()`, cuando `--enable-bfs` esté activo, descartar enlaces que terminen en extensiones estáticas o binarias:
     `{".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".zip", ".rar", ".tar", ".gz", ".exe", ".mp4", ".mp3", ".docx", ".xlsx", ".pptx"}`.

### 3.3 Proveedores v1 implementados

| Proveedor | Estrategia activa | Reglas de extracción relevantes |
|---|---|---|
| **Microsoft Learn** (`ms_learn.py`) | API REST de catálogo | `learningPaths` por defecto; `modules` solo con `--enable-modules`. La categoría se prioriza por `subjects`, `products`, `roles` y, finalmente, título; los slugs pasan a etiquetas limpias. |
| **OpenLearn** (`openlearn.py`) | Sitemap de cursos `.xml.gz`, índice XML y catálogo paginado de respaldo | Una ficha individual se procesa directamente. En catálogo, las fichas pasan por `extruct` y luego OpenGraph/DOM; el certificado requiere evidencia explícita en el HTML. |
| **Aprende.org** (`aprende.py`) | API JSON pública con `Crawler` | Detalle consultado perezosamente solo para los cursos que se emitirán; descripción ausente permanece `None`. HTTP/JSON inválidos se reportan como errores técnicos. |
| **Cisco NetAcad** (`netacad.py`) | Playwright sobre catálogo SPA | Espera los enlaces renderizados y emite solo tarjetas con `Price: Free` o `Gratis`; no consulta `cperf.netacad.com`. |

HubSpot Academy se retiró a `legacy/` después de que el sondeo confirmara que su sitemap ya no publicaba rutas `/courses/` y la shell HTML española carecía de datos estáticos de curso.

### 3.4 Suite offline y criterios de aceptación

* `tests/test_providers.py` cubre los cuatro proveedores con mocks HTTP/Playwright y cortesía puesta a cero en pruebas; la suite estándar no accede a Internet.
* Criterios de aceptación: `uv run pytest -v`, `uv run ruff check .` y `uv run mypy cli.py config.py schemas/ exporters/ utils/ core/ providers/ tests/` sin errores.
* Los smoke tests manuales de proveedor ejecutan:
  ```bash
  uv run cursodex run -p ms_learn --limit 3 --output -
  uv run cursodex run -p openlearn --limit 3 --output -
  uv run cursodex run -p aprende --limit 3 --output -
  uv run cursodex run -p netacad --limit 3 --output -
  ```
  Cada ejecución debe producir JSON-LD válido en `stdout` y un `run_summary` en `stderr`; `exit_code: 0` requiere al menos un curso válido.

---

## 4. Hoja de Ruta de Integración del Ecosistema Completo (Hitos 1 al Final)

```
Ene 2027              Feb 2027              Mar 2027              Abr 2027
   |                     |                     |                     |
   +-- Hito 1 (31/01)    |                     |                     |
   |   Cierre Extractor  |                     |                     |
   |   Setup Omeka S     |                     |                     |
   |                     +-- Hito 2 (28/02)    |                     |
   |                     |   n8n Docker Local  |                     |
   |                     |   Read-Merge-PUT    |                     |
   |                     |                     +-- Hito 3 (15/03)    |
   |                     |                     |   Prod VPS Webmin   |
   |                     |                     |   Faceted Browse    |
   |                     |                     |   OAI-PMH Harvest   |
   |                     |                     |                     +-- Hito 4 (31/03)
   |                     |                     |                     |   Rutas IA Python
   |                     |                     |                     |
   |                     |                     |                     +-- Hito 5/Final (30/04)
   |                     |                     |                         Guest/Favorites
   |                     |                     |                         Memoria TFM
```

---

### Hito 1 (Fecha Límite: 31/01/2027) — Finalización del Extractor y Preparación de Omeka S

* **En este repositorio (`cursos`):**
  * Infraestructura `core/extractor.py` con `extruct` y crawler compartido completados.
  * Proveedores v1 completados: `ms_learn.py`, `openlearn.py`, `aprende.py` y `netacad.py`.
  * HubSpot retirado a `legacy/` por ausencia de fichas estáticas aprovechables.
  * Validar pruebas y análisis estático con los comandos del §3.4.
* **En el Servidor de Omeka S (`cursodex.com/omekas/`):**
  * **Ontologías:** Importar vocabulario oficial `Schema.org` (ontología RDF completa) y activar `Dublin Core` nativo.
  * **Módulos Oficiales y Open-Source a Instalar:**
    * `Custom Vocab` (o `Thesaurus`): Crear el vocabulario controlado `"Categorías Cursodex"` poblando exactamente las mismas etiquetas `canonical` declaradas en `mappings/vocab_map.yml`.
    * `Bulk Import` / `CSV Import`: Para cargas manuales de contingencia.
    * `Bulk Edit`: Para moderación por lotes en la bandeja de entrada.
    * `Advanced Search` y `Faceted Browse`: Configuración del motor de búsqueda y facetas.
    * `OAI-PMH Repository`: Exposición del repositorio para recolectores OAI (`oai_dc`).
  * **Plantilla de Recurso (*Resource Template*):**
    * Crear la plantilla **`Curso`** asociada a la clase `schema:Course`.
    * Mapear todas las propiedades especificadas en `ARCHITECTURE.md` §6.1, marcando `schema:identifier` (hash) y `schema:dateModified` como privadas.
  * **Credenciales API REST:**
    * Generar par de claves de servicio en la cuenta de administración de Omeka S: `key_identity` y `key_credential`.

---

### Hito 2 (Fecha Límite: 28/02/2027) — Orquestación de Ingesta en `n8n` (Localhost Docker Primero)

El desarrollo del pipeline de orquestación se realiza inicialmente en local con Docker Compose antes de pasar al VPS.

#### Arquitectura de Ejecución Desacoplada
* **Estrategia Recomendada (GitHub Actions Worker):**
  * Para no saturar la CPU y memoria RAM del VPS (donde residen Omeka S, MySQL y Apache), y para evitar que las IPs estáticas de datacenter sean bloqueadas por los proveedores educativos, el extractor CLI se ejecuta en GitHub Actions mediante un workflow programado (`cron`).
  * Al finalizar con éxito, el runner de GitHub Actions emite un webhook `POST` autenticado hacia `n8n` enviando el archivo JSON-LD como payload o enlace de descarga.
* **Estrategia Alternativa (Contenedor Worker Docker con SSH):**
  * Contenedor Docker dedicado en la red interna de n8n, configurado con `shm_size: '1gb'` para Playwright, invocado por n8n mediante el nodo *Execute Command* o SSH.

#### Lógica Exacta del Flujo de Trabajo en `n8n`

```
[Webhook / Cron Trigger]
           |
           v
[Validar exit_code de run_summary]
   |--> exit_code == 1: [Alerta de Error Telegram/Discord] -> Abortar
   |--> exit_code == 2: [Log: Cero cursos sin error] -> Fin
   |--> exit_code == 0: Continuar
           |
           v
[Descarga Paginada de Omeka S: GET /api/items?per_page=100]
           |
           v
[Construir Índice de Identidad en Memoria: canonical_url -> {omeka_id, content_hash}]
           |
           v
[Comparar cada curso del JSON-LD contra el Índice]
   |
   +---> NO existe canonical_url  ======> [NUEVO: Alta]
   |
   +---> Existe y mismo hash      ======> [SIN CAMBIOS: Omitir / Actualizar fecha]
   |
   +---> Existe y distinto hash   ======> [MODIFICADO: Actualización]
           |
           +-----------------------------+
           |                             |
           v                             v
   [Preparar POST]               [Patrón Read-Merge-PUT]
   - o:is_public: false          1. GET /api/items/<omeka_id> (Ítem completo)
   - Asignar Resource Template   2. Fusionar cambios sobre el payload real
   - Eliminar _cursodex_meta     3. Actualizar schema:dateModified
   - Enviar a /api/items         4. PUT /api/items/<omeka_id> (Completo)
           |                             |
           +--------------+--------------+
                          |
                          v
        [Lotes de 5 ítems + Pausa 300 ms]
                          |
                          v
        [Bandeja de Entrada en Omeka S]
        - Curador modera is_public: false
        - Bulk Edit aprueba y publica (is_public: true)
```

1. **Gestión de Respuestas y Códigos de Salida:**
   * n8n evalúa el `exit_code` del `run_summary` en `stderr`. Si es `1`, notifica el fallo técnico y detiene el flujo. Si es `2`, finaliza pacíficamente.
2. **Descarga Paginada del Catálogo Existente:**
   * Consulta recursiva a `GET https://cursodex.com/omekas/api/items?per_page=100` con autenticación mediante query parameters (`key_identity` y `key_credential`).
   * Almacena en memoria el mapa de claves:
     `canonical_url (schema:url)` $\to$ `{omeka_id, content_hash (schema:identifier), is_public}`.
3. **Change Detection (Detección Determinista de Cambios):**
   * Compara el `content_hash` del JSON-LD contra el hash registrado en `schema:identifier` (`urn:cursodex:sha256:...`).
   * Si no existe: clasifica como **Alta Nueva**.
   * Si existe y los hashes coinciden: clasifica como **Sin Cambios** (se descarta o solo se actualiza `schema:dateModified`).
   * Si existe y los hashes difieren: clasifica como **Actualización**.
4. **Regla de Inserción (Altas):**
   * Todo curso nuevo se envía con `"o:is_public": false` y el ID numérico de la plantilla `Curso`.
   * Se elimina la clave privada `_cursodex_meta` antes del envío para cumplir estrictamente con la API REST de Omeka S.
5. **Regla de Actualización Obligatoria (Patrón Read-Merge-PUT):**
   * **PROHIBICIÓN:** Omeka S no admite `PATCH` parcial. Un `PUT` con payload incompleto elimina todas las propiedades omitidas.
   * **Flujo seguro:**
     1. `GET /api/items/<omeka_id>`: Descargar la representación completa del recurso en Omeka S.
     2. Merge: Sobrescribir las propiedades normalizadas nuevas preservando asignaciones manuales del curador (ej. colecciones, tags internos, estado de visibilidad si ya estaba publicado).
     3. Actualizar `schema:dateModified` con el nuevo `last_seen_at`.
     4. `PUT /api/items/<omeka_id>`: Enviar el objeto completo actualizado.
6. **Throttling y Control de Concurrencia:**
   * Enviar las peticiones hacia Omeka S en lotes de 5 elementos con pausas de 300 ms entre llamadas para no saturar los workers de PHP-FPM ni exceder los límites de conexión de MySQL.
7. **Bandeja de Curaduría y Moderación:**
   * Los cursos nuevos ingresan como borrador privado (`is_public: false`).
   * El curador accede a `cursodex.com/omekas/admin/item`, filtra por los ítems con `needs_review: true` (señalizados con notas en la descripción o categoría pendiente), asigna la categoría correspondiente y realiza la publicación masiva mediante el módulo `Bulk Edit` marcando `"o:is_public": true`.

---

### Hito 3 (Fecha Límite: 15/03/2027) — Catálogo Público y Paso a Producción en VPS con Webmin

* **Configuración del Portal Público en Omeka S:**
  * Configurar navegación facetada lateral (`Faceted Browse`) por:
    1. Categoría temática (`schema:about`).
    2. Proveedor / Plataforma (`schema:provider`).
    3. Nivel educativo (`schema:educationalLevel`).
    4. Idioma (`schema:inLanguage`).
    5. Tipo de certificación (`schema:educationalCredentialAwarded`).
    6. Etiquetas técnicas (`schema:keywords`).
* **Verificación de Estándares Semánticos:**
  * Validar marcado Schema.org embebido en las vistas públicas mediante el validador oficial de Schema.org y Google Rich Results.
  * Validar el endpoint OAI-PMH cosechando registros con prefijo Dublin Core:
    `https://cursodex.com/omekas/oai-pmh?verb=ListRecords&metadataPrefix=oai_dc`.
* **Despliegue Seguro en VPS con Webmin (Linux Ubuntu):**
  * **Seguridad de Puertos Docker:**
    * Los puertos de n8n o contenedores auxiliares deben exponerse **únicamente en loopback** (`127.0.0.1:5678:5678`), impidiendo que Docker manipule `iptables` y exponga servicios directamente a internet saltándose el firewall de Webmin.
  * **VirtualHost y Reverse Proxy:**
    * Crear VirtualHost Apache/Nginx administrado desde Webmin con certificado SSL Let's Encrypt automático.
    * Configurar Reverse Proxy hacia `http://127.0.0.1:5678/` habilitando el soporte de WebSockets (`proxy_wstunnel` en Apache) requerido por la interfaz de n8n.
  * **Variables de Entorno Críticas para n8n:**
    * `EXECUTIONS_DATA_PRUNE=true`
    * `EXECUTIONS_DATA_MAX_AGE=168` (poda automática de historial tras 7 días para evitar colapso de disco).
    * `WEBHOOK_URL=https://n8n.cursodex.com/`
  * **Mantenimiento y Resiliencia del Sistema:**
    * Configurar límite de logs en Docker (`max-size: "10m"`, `max-file: "3"`).
    * Configurar archivo Swap de 2 GB en el VPS para amortiguar picos de memoria durante renderizados con Playwright o imports masivos.
    * Configurar tareas programadas nocturnas en Cron de Webmin: volcado de base de datos MySQL de Omeka S (`mysqldump`) y copia de seguridad de flujos de n8n.

---

### Hito 4 (Fecha Límite: 31/03/2027 — Prioridad Media) — Rutas de Aprendizaje Especializadas con Python + IA

* **Objetivo:** Generar itinerarios de formación multi-proveedor estructurados pedagógicamente (ej. *"Ruta Completa: De Cero a Analista de Datos"*).
* **Script Independiente (`routes/generate_learning_paths.py`):**
  * Consulta la API REST de Omeka S para obtener los cursos públicos aprobados (`GET /api/items?is_public=true`).
  * Utiliza la librería `instructor` junto con Pydantic v2 sobre un LLM (Gemini API o compatible) para agrupar cursos en secuencias pedagógicas de complejidad creciente (Principiante $\to$ Intermedio $\to$ Avanzado), evaluando `educational_level`, `keywords` y `course_prerequisites`.
* **Candado Anti-Alucinación Estricto:**
  * El script valida que cada identificador (`o:id`) propuesto por el LLM exista obligatoriamente en la lista real de cursos recuperados de Omeka S.
  * Si un ID no existe o fue alucinado, la ruta se descarta o se repara antes de persistir.
* **Persistencia Semántica en Omeka S:**
  * Las rutas aprobadas se inyectan en Omeka S como recursos de tipo `schema:ItemList`.
  * Cada elemento del array `schema:itemListElement` almacena la URI interna del ítem de curso correspondiente en Omeka S.

---

### Hito 5 (Fecha Límite: 15/04/2027 — Buffer) e Hito Final (30/04/2027) — Experiencia de Usuario y Memoria TFM

* **Hito 5 (Buffer de Estabilización y Mejoras Opcionales):**
  * Instalación y configuración de los módulos `Guest` y `Selection` en Omeka S para permitir registro voluntario de usuarios y guardado de cursos en listas de favoritos.
  * Formulario público de sugerencias de cursos para la comunidad.
* **Hito Final (30/04/2027 — Entrega del TFM):**
  * Congelación de código y pruebas finales de estrés y accesibilidad (WCAG 2.1).
  * Extracción de métricas finales: volumen total de cursos indexados, distribución por categorías CINE-F/DigComp, tasa de descarte de cursos no gratuitos y tiempos medios de ingesta.
  * Redacción y cierre de la memoria académica del TFM, documentando la arquitectura de datos abiertos, interoperabilidad semántica y el pipeline de curaduría.

---

## 5. Tabla Maestra de Riesgos y Planes de Mitigación

| Riesgo Técnico | Severidad | Probabilidad | Plan de Mitigación |
| :--- | :---: | :---: | :--- |
| **Bloqueo antibot en CI/VPS (403/Cloudflare)** en Aprende o NetAcad | Alta | Media | Ejecutar desde un worker desacoplado; OpenLearn queda como proveedor activo complementario basado en sitemap y extracción estática. |
| **Colapso de RAM en VPS** por procesos huérfanos de Chromium | Alta | Media | Configurar Playwright context manager reutilizable, asignar Swap de 2GB en VPS y ejecutar Playwright prioritariamente en runners externos de CI. |
| **Borrado accidental de metadatos en Omeka S** por actualizaciones | Crítica | Baja | Obligatoriedad estricta del patrón **Read-Merge-PUT** en n8n (`GET` ítem completo previo a cualquier actualización; prohibido `PATCH`). |
| **Contaminación semántica de facetas** con `"Pendiente_Categoria"` | Media | Alta | Regla activa en `exporters/`: omisión de `schema:about` y `dcterms:subject` en el RDF público cuando no hay match formal; resolución en moderación. |
| **Falsos positivos de cursos de pago** camuflados como gratuitos | Alta | Media | Regla anti-pago en `Course`: valida `is_accessible_for_free=True` y categoriza credenciales vía `AccessType`; rechaza modelos de suscripción de pago. |
| **Rotura de tuberías CLI en n8n** por caracteres de escape o logs | Alta | Baja | Contrato Unix blindado: `stdout` emite exclusivamente JSON puro; 100% de logs y resúmenes redirigidos a `stderr`; salida con códigos `0/1/2`. |

---

## 6. Procedimiento de Verificación y Comandos de Control

Para asegurar la integridad continua del repositorio en cualquier entorno, todo desarrollo posterior debe validar los siguientes comandos sin excepciones:

```bash
# 1. Sincronización exacta del entorno virtual (congelado)
uv sync --frozen

# 2. Instalación de binarios de Playwright (solo si se ejecutan scrapers dinámicos)
uv run playwright install chromium

# 3. Ejecución de la suite completa de pruebas unitarias y de subproceso
uv run pytest -v

# 4. Verificación de estilo y conformidad con linters
uv run ruff check .

# 5. Comprobación estricta de tipado estático
uv run mypy cli.py config.py schemas/ exporters/ utils/ core/ providers/
```
