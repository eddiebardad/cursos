# Guía de Inicio y Directrices para Agentes de IA (AGENTS.md)

Este repositorio (`cursos` / `cursodex-extractor`) constituye el **motor de extracción, normalización y serialización semántica** del proyecto académico **Cursodex** (TFM).

Cualquier agente de IA o desarrollador que trabaje en este proyecto en Visual Studio Code o en cualquier otro entorno automatizado **debe seguir estrictamente esta guía**.

---

## 1. Contexto y Orden de Lectura Obligatoria

El repositorio completó los Pasos 1, 2, 3 y 4A–4C. Los cuatro proveedores v1 activos son `ms_learn`, `openlearn`, `aprende` y `netacad`.

Antes de realizar cambios, diagnosticar errores o planificar tareas, consulta en este orden:

1. [ARCHITECTURE.md](./ARCHITECTURE.md): modelo semántico `Course`, ontologías Schema.org y Dublin Core, contratos de exportación y Omeka S v4+.
2. [PLAN.md](./PLAN.md): estado de los Pasos 1–4C e hitos de integración con `n8n` y Omeka S.
3. [.agent/rules/cursodex.md](./.agent/rules/cursodex.md): guardrails permanentes del repositorio.

---

## 2. Los 17 Guardrails Críticos del Proyecto (G1 a G17)

* **G1 (Gestor `uv` exclusivo):** Prohibido usar `pip`, `conda` o `poetry`. Instalar entorno con `uv sync --frozen --link-mode=copy`. Ejecutar comandos con `uv run ...`.
* **G2 (Contrato Unix absoluto):** **Prohibido `print()`** en runtime. `sys.stdout` queda reservado para datos estructurados limpios: JSON-LD con `--output -` por defecto o CSV si se especifica `--format csv`. `sys.stderr` recibe 100% de logs y `run_summary` estructurado.
* **G3 (Códigos de salida semánticos):**
  * `0`: $\ge 1$ cursos extraídos con éxito.
  * `2`: 0 cursos extraídos sin error técnico (alerta temprana para n8n).
  * `1`: Excepción, fallo de red o sintaxis CLI errónea.
  * Usar siempre `raise typer.Exit(code=N)`.
* **G4 (Herramienta Unix Stateless):** Prohibido añadir frameworks web (FastAPI, Flask, Django), bases de datos locales (SQLite, PostgreSQL, MongoDB, Redis) o clientes HTTP que apunten directamente a Omeka S. Esa orquestación le corresponde a `n8n`.
* **G5 (Sin `rdflib`):** Prohibido añadir `rdflib` como dependencia directa o importarlo. Toda validación y serialización se efectúa con Pydantic v2 y diccionarios nativos.
* **G6 (Pydantic v2 estático):** El modelo `Course` en `schemas/models.py` debe ser estático. Prohibido `create_model()` dinámico o monkey-patching.
* **G7 (Extracción semántica primaria):** Usar `extruct` (`json-ld`, `microdata`, `opengraph`) priorizando `schema:Course`. `BeautifulSoup4` solo actúa como fallback DOM.
* **G8 (Crawler BFS desactivado por defecto):** `crawl_site()` requiere `--enable-bfs` explícito. Si una URL carece de adaptador y no se pasó el flag, emitir error a `stderr` y salir con código `1`.
* **G9 (Cortesía y User-Agent):** Pausa entre requests `config.COURTESY_DELAY` (1.0s) y User-Agent obligatorio: `CursodexBot/1.0 (+https://cursodex.com; academic research index)`.
* **G10 (Vocabulario controlado CINE-F + DigComp):** Mapeo declarado en `mappings/vocab_map.yml`, evaluado **de más específico a más general** con límites de palabra (`match_synonym_boundary`). Si no hay coincidencia $\to$ `category = "Pendiente_Categoria"` y `needs_review = True`.
* **G11 (`legacy/` en `.gitignore`):** Todo archivo obsoleto o de prueba previa reside en `legacy/` fuera de Git.
* **G12 (`--output -`):** Infiere automáticamente `--format jsonld` si no se especificó formato.
* **G13 (Contrato Omeka S v4+):** Cada nodo de propiedad incluye `"property_id": "auto"`. Identificadores y fechas privadas con `"is_public": false`. No incluir `"o:id"` en `@type`. Si `category == "Pendiente_Categoria"`, **omitir** `schema:about` y `dcterms:subject` en el grafo RDF público.
* **G14 (Filtro anti-pago estricto):** Todo curso debe tener `is_accessible_for_free=True`. Rechazar con `ValueError` modelos de pago o pruebas temporales. Clasificar credenciales mediante enum `AccessType`.
* **G15 (Microsoft Learn):** Extraer solo `learningPaths` por defecto; `modules` requiere `--enable-modules`. Mapear duraciones a ISO 8601.
* **G16 (Identidad y Cambios):**
  * `canonical_url`: https forzado, dominios en minúsculas, stripping de puertos `:80` y `:443`, sin parámetros de tracking (`utm_*`, etc.) y anti-redirección de portada (rechaza rutas raíz vacías).
  * `content_hash`: SHA-256 sobre campos descriptivos/pedagógicos con listas ordenadas case-insensitive (`key=str.lower`), excluyendo timestamps y notas.
* **G17 (CSV sin BOM):** Codificación UTF-8 pura sin BOM; columnas separadas por coma, listas multivalor por `;` y puntos y comas internos sustituidos por comas antes de concatenar.

El catálogo v1 solo registra `ms_learn`, `openlearn`, `aprende` y `netacad`; Microsoft Learn extrae `learningPaths` por defecto.

---

## 3. Comandos de Verificación Innegociables

Antes de dar cualquier tarea por completada o sugerir un commit, ejecuta y comprueba:

```bash
# 1. Ejecutar suite de pruebas unitarias y subprocesos
uv run pytest -v

# 2. Comprobar linters y estilo
uv run ruff check .

# 3. Comprobar tipado estático
uv run mypy cli.py config.py schemas/ exporters/ utils/ core/ providers/ tests/
```
