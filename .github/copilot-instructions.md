# Instrucciones para GitHub Copilot (Cursodex)

Este repositorio (`cursos`) es el motor CLI de extracción y normalización semántica para el proyecto académico **Cursodex**.

## Documentación y Contexto Esencial
Antes de generar o modificar código en este repositorio, consulta obligatoriamente:
1. `ARCHITECTURE.md`: Contratos de datos, modelo Pydantic v2 `Course`, ontologías Schema.org y Dublin Core, y especificación Omeka S v4+.
2. `PLAN.md`: Hoja de ruta técnica maestra (Paso 4 de proveedores v1 e hitos 1 a 5 hacia producción).
3. `AGENTS.md` y `.agent/rules/cursodex.md`: Guardrails inquebrantables del agente.

## Guardrails Críticos de Implementación
- **Entorno:** Exclusivamente `uv` (`uv add`, `uv run ...`). Prohibido `pip`, `conda` o `poetry`.
- **Contrato Unix:** Prohibido `print()`. `stdout` reservado exclusivamente para JSON puro (`--output -`). Todos los logs van a `stderr` vía `utils/logger.py`.
- **Códigos de salida:** `0` (éxito con $\ge 1$ cursos), `2` (0 cursos sin error técnico), `1` (fallo de red, error o argumentos inválidos).
- **Alcance Stateless:** Prohibido añadir frameworks web (FastAPI/Flask), bases de datos locales (SQLite/Postgres) o clientes HTTP que apunten a Omeka S (n8n gestiona esa capa).
- **Sin `rdflib`:** La validación semántica se hace con Pydantic v2 estático y diccionarios nativos.
- **Extracción:** Usar `extruct` (`json-ld`, `microdata`, `opengraph`) priorizando `schema:Course`; `BeautifulSoup4` solo como fallback.
- **Contrato Omeka S v4+:** Todo valor de propiedad en JSON-LD debe contener `"property_id": "auto"`. Si `category == "Pendiente_Categoria"`, omitir `schema:about` y `dcterms:subject` en el grafo público.
- **Filtro Anti-Pago:** Cursos con costo o prueba temporal deben ser rechazados en validación con `ValueError`.

## Verificación de Código
Todo cambio debe validar con 0 errores:
```bash
uv run pytest -v
uv run ruff check .
uv run mypy cli.py config.py schemas/ exporters/ utils/ core/ providers/
```
