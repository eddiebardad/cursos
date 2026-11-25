# Cursodex Extractor (`cursodex-extractor`)

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Checked with mypy](https://www.mypy-lang.org/static/mypy_badge.svg)](https://mypy-lang.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Motor CLI ligero, sin estado (*stateless*) y de alta fidelidad semántica para la extracción, normalización y exportación de cursos gratuitos en línea.**  
Diseñado como el componente de ingesta del proyecto académico **Cursodex** (TFM).

El sistema extrae metadatos educativos de plataformas abiertas (Microsoft Learn, HubSpot Academy, Aprende.org, Cisco NetAcad), normaliza la información conforme a estándares ontológicos internacionales (**Schema.org** `schema:Course` y espejo **Dublin Core** `dcterms:*`) y genera salidas listas para orquestación en **n8n** e importación en la API REST de **Omeka S v4+** (`cursodex.com/omekas/`).

---

## Documentación Maestra del Proyecto

Para una comprensión profunda de las especificaciones, ontologías y hoja de ruta:

* [ARCHITECTURE.md](ARCHITECTURE.md): Arquitectura del sistema, especificación del modelo `Course`, contratos JSON-LD para Omeka S v4+, mapeo CINE-F 2013 / DigComp 2.2 y reglas anti-falsos gratis.
* [PLAN.md](PLAN.md): Hoja de ruta maestra end-to-end, estado actual post-Paso 3, especificación del Paso 4 (proveedores v1) e hitos hacia producción en VPS.
* [AGENTS.md](AGENTS.md): Reglas inquebrantables y guardrails permanentes para agentes de IA en VS Code.

---

## Requisitos del Sistema

* **Python 3.11 o superior** (probado y validado en Python 3.11 y 3.14).
* **[uv](https://docs.astral.sh/uv/)** como gestor de paquetes y entornos virtuales (*prohibido el uso directo de `pip`, `conda` o `poetry`*).
* Sistema operativo compatible: Linux, macOS o Windows (PowerShell).

---

## Instalación Rápida y Reproducible

Clona el repositorio e instala el entorno congelado con `uv`:

```bash
# 1. Clonar el repositorio
git clone https://github.com/eddiebardad/cursos.git
cd cursos

# 2. Sincronizar el entorno virtual exacto (uv.lock congelado)
uv sync --frozen --link-mode=copy

# 3. Instalar binarios de Playwright Chromium (requerido para proveedores dinámicos)
uv run playwright install chromium
```

---

## Uso de la Herramienta CLI

El extractor cumple con la filosofía de herramientas Unix: emite datos limpios por `stdout` (para tuberías) y redirige todos los logs, advertencias y resúmenes estructurados a `stderr`.

### 1. Extracción con Tubería a `stdout` (Formato JSON-LD por defecto)
Ideal para integración directa con `n8n` o redirección a herramientas como `jq`:
```bash
# Extraer hasta 5 cursos de Microsoft Learn directamente a stdout
uv run cursodex run --provider mslearn --limit 5 --output -
```

### 2. Exportación hacia Archivo JSON-LD (Omeka S REST API v4+)
Genera un archivo JSON-LD con `"property_id": "auto"`, `"o:is_public": false` y metadatos privados `_cursodex_meta`:
```bash
uv run cursodex run --provider hubspot --limit 20 --output resultados.jsonld
```

### 3. Exportación hacia Archivo CSV (Omeka S Bulk Import)
Genera un archivo CSV en codificación UTF-8 sin BOM, con cabeceras `schema:*` y `dcterms:*`, y separador de listas `;`:
```bash
uv run cursodex run --provider aprende --output cursos_aprende.csv --format csv
```

### 4. Extracción por URL Específica
El CLI detecta automáticamente el proveedor correspondiente según el dominio:
```bash
uv run cursodex run --url "https://aprende.org/cursos/view/123" --output -
```

### 5. Opciones Disponibles en el CLI
```text
Opciones:
  -u, --url TEXT           URL inicial para extraer o rastrear.
  -p, --provider TEXT      Forzar un adaptador registrado por nombre (mslearn, hubspot, aprende, netacad).
  -o, --output TEXT        Ruta de salida o '-' para stdout estructurado [default: results.csv].
  -f, --format TEXT        Formato explícito ('jsonld' o 'csv').
  -l, --limit INTEGER      Límite máximo de cursos a extraer (0 = sin límite) [default: 0].
  --render                 Habilitar Playwright Chromium para renderizar SPAs / JavaScript.
  --enable-bfs             Habilitar rastreo genérico BFS cuando una URL no tiene adaptador.
  --enable-modules         Extraer micro-módulos atómicos en proveedores que lo admitan (ej. MS Learn).
  --max-pages INTEGER      Límite de páginas a spider en modo BFS [default: 100].
  --help                   Muestra el menú de ayuda y sale limpiamente.
```

---

## Códigos de Salida Semánticos

El CLI garantiza códigos de retorno estandarizados para control en orquestadores (`n8n`, scripts Bash):

| Código | Significado | Comportamiento |
| :---: | :--- | :--- |
| **`0`** | **Éxito** | $\ge 1$ cursos extraídos y exportados con éxito. |
| **`2`** | **Alerta Temprana** | 0 cursos extraídos sin fallo de red (posible cambio en estructura del proveedor). Emite estructura vacía `[]`. |
| **`1`** | **Fallo Técnico** | Excepción, fallo de red, URL sin adaptador sin `--enable-bfs` o sintaxis CLI errónea. |

---

## Estructura del Proyecto

```text
cursos/
├── ARCHITECTURE.md          # Especificación formal de arquitectura y contratos semánticos
├── PLAN.md                  # Hoja de ruta técnica maestra (Paso 4 e Hitos 1 a 5)
├── AGENTS.md                # Directrices y guardrails para agentes en VS Code
├── pyproject.toml           # Dependencias fijadas y configuración de herramientas uv/ruff/mypy
├── uv.lock                  # Lockfile determinista y reproducible
├── cli.py                   # Punto de entrada Typer/Click con contrato Unix y exit codes
├── config.py                # Configuración global (timeouts, User-Agent, cortesía)
├── core/
│   ├── crawler.py           # Cliente HTTP httpx con pausas de cortesía y Playwright
│   ├── parser.py            # Parser fallback DOM y utilidades HTML
│   └── exceptions.py        # Excepciones técnicas del dominio
├── exporters/
│   ├── base.py              # Clase base abstracta de exportadores
│   ├── jsonld_exporter.py   # Exportador JSON-LD compatible con Omeka S v4+ y OAI-PMH
│   └── csv_exporter.py      # Exportador CSV UTF-8 sin BOM con separador ';'
├── mappings/
│   └── vocab_map.yml        # Vocabulario controlado CINE-F 2013 + DigComp 2.2
├── providers/
│   ├── base.py              # Clase base ProviderBase con registro automático
│   ├── ms_learn.py          # Adaptador API Microsoft Learn (en desarrollo Paso 4)
│   ├── hubspot.py           # Adaptador HubSpot Academy
│   ├── aprende.py           # Adaptador API Aprende.org (Fundación Carlos Slim)
│   └── netacad.py           # Adaptador Cisco Networking Academy
├── schemas/
│   └── models.py            # Modelo Pydantic v2 Course, validaciones, content_hash SHA-256
├── tests/
│   ├── test_models.py       # Pruebas unitarias de modelos, canonización, hashes e imágenes
│   └── test_exporters_and_cli.py # Pruebas de exportadores y subprocesos reales del SO
└── utils/
    └── logger.py            # Logger idempotente configurado 100% a stderr y run_summary
```

---

## Verificación de Calidad y Pruebas

Para validar el funcionamiento del proyecto antes de commitear:

```bash
# Ejecutar suite de pruebas unitarias y de integración
uv run pytest -v

# Ejecutar linter y formateador
uv run ruff check .

# Ejecutar comprobador estático de tipos
uv run mypy cli.py config.py schemas/ exporters/ utils/ core/ providers/
```

---

## Licencia

Distribuido bajo la licencia **MIT**. Consulta `LICENSE` para más información.
