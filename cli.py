"""
cli.py
==============================================================================
Punto de entrada de línea de comandos para Cursodex (v0.5.0).

Cumple estrictamente el contrato Unix:
1. stdout: reservado para datos estructurados limpios (--output -).
2. stderr: 100% de logs, errores, help text y resumen estructurado (run_summary).
3. Códigos de salida semánticos:
   0: >= 1 cursos extraídos con éxito.
   2: 0 cursos extraídos sin excepción técnica (alerta temprana para n8n).
   1: Error crítico, fallo de red, URL no soportada sin BFS o argumentos inválidos.
==============================================================================
"""

import json
import re
import sys
import time
from typing import Annotated

import click
import typer

from core.crawler import crawl_site
from core.manifest import load_provider_manifest
from core.strategy import StrategyRunner
from exporters.base import BaseExporter, deduplicate_courses
from exporters.csv_exporter import CSVExporter
from exporters.jsonld_exporter import JSONLDExporter
from providers import get_provider_by_name, get_provider_for_url
from schemas.models import Course
from utils.logger import emit_run_summary, get_logger

logger = get_logger(__name__)
_PROVIDER_MANIFEST = load_provider_manifest()


def _provider_choices() -> str:
    return ", ".join([*_PROVIDER_MANIFEST, "all"])


def _normalized_name(value: str) -> str:
    return re.sub(r"[\s_-]+", "", value).casefold()


def _manifest_id_for_provider(
    provider_name: str,
    provider_instance: object,
) -> str | None:
    names = {
        _normalized_name(provider_name),
        _normalized_name(str(getattr(provider_instance, "provider_name", ""))),
    }
    aliases = getattr(provider_instance, "provider_aliases", ())
    names.update(_normalized_name(alias) for alias in aliases)
    for provider_id, definition in _PROVIDER_MANIFEST.items():
        if names.intersection(
            {_normalized_name(provider_id), _normalized_name(definition.name)}
        ):
            return provider_id
    return None


def _scrape_all_providers(
    limit: int,
    enable_modules: bool,
    skip_waf_sensitive: bool,
) -> list[Course]:
    runner = StrategyRunner(_PROVIDER_MANIFEST)
    courses: list[Course] = []
    for provider_id, definition in _PROVIDER_MANIFEST.items():
        if skip_waf_sensitive and definition.datacenter_waf_sensitive:
            logger.info("Skipping WAF-sensitive provider: %s", provider_id)
            continue
        instance = get_provider_by_name(provider_id)
        if instance is None:
            raise RuntimeError(f"No adapter registered for provider {provider_id!r}")
        remaining = limit - len(courses) if limit > 0 else 0
        courses.extend(
            runner.run(
                provider_id,
                instance,
                getattr(instance, "default_url", None) or definition.base_url,
                limit=remaining,
                enable_modules=enable_modules,
            )
        )
        if limit > 0 and len(courses) >= limit:
            return courses[:limit]
    return courses

app = typer.Typer(
    help=f"Cursodex Extractor v0.5.0 — extracción sin estado de cursos gratuitos ({_provider_choices()}).",
    pretty_exceptions_enable=False,
    add_completion=False,
    rich_markup_mode=None,
)


def _resolve_exporter(output_path: str, format_param: str | None) -> BaseExporter:
    """Determina el exportador adecuado según el flag o la extensión."""
    if format_param:
        fmt = format_param.lower().strip()
        if fmt == "jsonld" or fmt == "json":
            return JSONLDExporter()
        elif fmt == "csv":
            return CSVExporter()
        else:
            logger.error(f"Formato no reconocido: '{format_param}'. Use 'csv' o 'jsonld'.")
            raise ValueError(f"Formato inválido '{format_param}'")

    # Si se dirige a stdout (-), por defecto emitir JSON-LD estructurado
    if output_path == "-":
        return JSONLDExporter()

    # Si es archivo, inferir por extensión
    if output_path.lower().endswith(".json") or output_path.lower().endswith(".jsonld"):
        return JSONLDExporter()
    return CSVExporter()


def _execute_scrape(
    url: str | None,
    provider: str | None,
    output: str,
    format_param: str | None,
    limit: int,
    render: bool,
    enable_bfs: bool,
    enable_modules: bool,
    max_pages: int,
    skip_waf_sensitive: bool = False,
) -> None:
    start_time = time.perf_counter()
    provider_instance = None
    target_url = url
    provider_name: str | None = None
    courses: list[Course] = []

    try:
        # 1. Validación inicial de URL y Provider
        is_all_providers = bool(provider and provider.casefold() == "all")
        if is_all_providers and target_url:
            logger.error("--provider all cannot be combined with --url.")
            emit_run_summary(
                provider=provider,
                url=target_url,
                courses_extracted=0,
                needs_review_count=0,
                exit_code=1,
                elapsed_seconds=time.perf_counter() - start_time,
            )
            raise typer.Exit(code=1)
        if not target_url and not provider:
            sys.stderr.write("Error: Debe especificar al menos una URL (--url / -u) o un proveedor (--provider / -p).\n")
            emit_run_summary(
                provider=None,
                url=None,
                courses_extracted=0,
                needs_review_count=0,
                exit_code=1,
                elapsed_seconds=0.0,
            )
            raise typer.Exit(code=1)

        # 2. Resolución del proveedor si fue especificado explícitamente
        if provider and not is_all_providers:
            provider_instance = get_provider_by_name(provider)
            if not provider_instance:
                logger.error(f"No se encontró ningún adaptador registrado con el nombre '{provider}'.")
                emit_run_summary(
                    provider=provider,
                    url=target_url,
                    courses_extracted=0,
                    needs_review_count=0,
                    exit_code=1,
                    elapsed_seconds=time.perf_counter() - start_time,
                )
                raise typer.Exit(code=1)

            provider_name = provider_instance.provider_name
            if not target_url and getattr(provider_instance, "default_url", None):
                target_url = provider_instance.default_url

            if not target_url:
                logger.error(f"El adaptador '{provider_name}' no define una URL por defecto. Especifique --url.")
                emit_run_summary(
                    provider=provider_name,
                    url=None,
                    courses_extracted=0,
                    needs_review_count=0,
                    exit_code=1,
                    elapsed_seconds=time.perf_counter() - start_time,
                )
                raise typer.Exit(code=1)

            logger.info(f"Adaptador forzado: {provider_name} | URL: {target_url}")
        elif is_all_providers:
            provider_name = "all"
            logger.info("Ejecutando todos los proveedores declarados en mappings/providers.yml.")
        else:
            # Detección automática por dominio de URL
            provider_instance = get_provider_for_url(target_url)  # type: ignore[arg-type]
            if provider_instance:
                provider_name = provider_instance.provider_name
                logger.info(f"Proveedor detectado automáticamente: {provider_name}")
            else:
                # Si no hay adaptador registrado, verificar si se autorizó explícitamente el BFS
                if not enable_bfs:
                    msg = (
                        f"Error: No existe un adaptador para la URL '{target_url}' y el crawler genérico BFS "
                        "está desactivado por defecto (ARCHITECTURE.md §9). "
                        "Especifique --enable-bfs para permitir el rastreo genérico.\n"
                    )
                    sys.stderr.write(msg)
                    sys.stderr.flush()
                    logger.error(msg.strip())
                    emit_run_summary(
                        provider=None,
                        url=target_url,
                        courses_extracted=0,
                        needs_review_count=0,
                        exit_code=1,
                        elapsed_seconds=time.perf_counter() - start_time,
                    )
                    raise typer.Exit(code=1)
                logger.info("Utilizando crawler genérico BFS (--enable-bfs activo).")

        # 3. Validación de renderizado con Playwright
        if render:
            try:
                import playwright  # noqa: F401
            except ImportError as err:
                logger.error(
                    "El modo render (--render) requiere Playwright instalado. "
                    "Ejecute: uv run playwright install"
                )
                emit_run_summary(
                    provider=provider_name,
                    url=target_url,
                    courses_extracted=0,
                    needs_review_count=0,
                    exit_code=1,
                    elapsed_seconds=time.perf_counter() - start_time,
                )
                raise typer.Exit(code=1) from err

        # 4. Instanciación del exportador
        try:
            exporter = _resolve_exporter(output, format_param)
        except ValueError as err:
            emit_run_summary(
                provider=provider_name,
                url=target_url,
                courses_extracted=0,
                needs_review_count=0,
                exit_code=1,
                elapsed_seconds=time.perf_counter() - start_time,
            )
            raise typer.Exit(code=1) from err

        # 5. Ejecución del scraping
        logger.info(
            "Iniciando extracción en %s (límite: %s)",
            target_url or "todos los proveedores",
            limit if limit > 0 else "sin límite",
        )

        if is_all_providers:
            courses.extend(
                _scrape_all_providers(
                    limit,
                    enable_modules,
                    skip_waf_sensitive,
                )
            )
        elif provider_instance:
            assert target_url is not None
            manifest_id = _manifest_id_for_provider(provider or "", provider_instance)
            if manifest_id:
                extracted = StrategyRunner(_PROVIDER_MANIFEST).run(
                    manifest_id,
                    provider_instance,
                    target_url,
                    limit=limit,
                    enable_modules=enable_modules,
                )
            else:
                extracted = list(
                    provider_instance.scrape(
                        target_url,
                        render=render,
                        limit=limit,
                        enable_modules=enable_modules,
                    )
                )
            for course in extracted:
                courses.append(course)
                if limit > 0 and len(courses) >= limit:
                    break
        else:
            assert target_url is not None
            courses.extend(
                crawl_site(
                    target_url,
                    max_pages=max_pages,
                    render=render,
                    limit=limit,
                )
            )

        courses = deduplicate_courses(courses)
        elapsed = time.perf_counter() - start_time
        needs_review_count = sum(1 for c in courses if c.needs_review)

        # 6. Evaluación de resultados y códigos de salida
        if not courses:
            # Si el destino es stdout (-), emitir estructura vacía válida (JSON array vacío o solo cabecera CSV)
            if output == "-":
                exporter.export([], output)

            logger.warning("No se encontraron registros de cursos válidos en la URL especificada.")
            emit_run_summary(
                provider=provider_name,
                url=target_url,
                courses_extracted=0,
                needs_review_count=0,
                exit_code=2,
                elapsed_seconds=elapsed,
            )
            raise typer.Exit(code=2)

        exporter.export(courses, output)
        logger.info(f"Extracción completada con éxito. {len(courses)} cursos exportados.")
        emit_run_summary(
            provider=provider_name,
            url=target_url,
            courses_extracted=len(courses),
            needs_review_count=needs_review_count,
            exit_code=0,
            elapsed_seconds=elapsed,
        )
        raise typer.Exit(code=0)

    except typer.Exit:
        raise
    except Exception as e:
        elapsed = time.perf_counter() - start_time
        logger.error(f"Error crítico de ejecución: {e}", exc_info=True)
        emit_run_summary(
            provider=provider_name,
            url=target_url,
            courses_extracted=len(courses),
            needs_review_count=sum(1 for c in courses if getattr(c, "needs_review", False)),
            exit_code=1,
            elapsed_seconds=elapsed,
        )
        raise typer.Exit(code=1) from e


@app.command("run")
def run_command(
    url: Annotated[
        str | None,
        typer.Option("--url", "-u", help="URL de catálogo o curso; el dominio detecta el proveedor."),
    ] = None,
    provider: Annotated[
        str | None,
        typer.Option("--provider", "-p", help=f"Proveedor: {_provider_choices()}."),
    ] = None,
    output: Annotated[
        str,
        typer.Option("--output", "-o", help="Archivo CSV/JSON-LD o '-' para stdout (JSON-LD por defecto)."),
    ] = "results.csv",
    format_param: Annotated[
        str | None,
        typer.Option("--format", "-f", help="csv o jsonld; si se omite, se infiere y '-' usa jsonld por defecto."),
    ] = None,
    limit: Annotated[
        int,
        typer.Option("--limit", "-l", help="Máximo de cursos válidos; 0 no limita."),
    ] = 0,
    render: Annotated[
        bool,
        typer.Option("--render", help="Renderizado JavaScript con Playwright; NetAcad siempre lo usa."),
    ] = False,
    enable_bfs: Annotated[
        bool,
        typer.Option("--enable-bfs", help="Activar BFS para sitios sin proveedor; apagado por defecto."),
    ] = False,
    enable_modules: Annotated[
        bool,
        typer.Option("--enable-modules", help="Incluir módulos de Microsoft Learn además de learningPaths."),
    ] = False,
    max_pages: Annotated[
        int,
        typer.Option("--max-pages", help="Máximo de páginas para el rastreador BFS genérico."),
    ] = 100,
    skip_waf_sensitive: Annotated[
        bool,
        typer.Option(
            "--skip-waf-sensitive",
            help="Omitir proveedores sensibles a WAF cuando --provider all.",
        ),
    ] = False,
) -> None:
    """Extrae cursos de los proveedores declarados y exporta CSV/JSON-LD."""
    _execute_scrape(
        url=url,
        provider=provider,
        output=output,
        format_param=format_param,
        limit=limit,
        render=render,
        enable_bfs=enable_bfs,
        enable_modules=enable_modules,
        max_pages=max_pages,
        skip_waf_sensitive=skip_waf_sensitive,
    )


@app.command("providers")
def providers_command(
    format_param: Annotated[
        str,
        typer.Option("--format", help="Formato de salida: table o json."),
    ] = "table",
) -> None:
    """Lista los proveedores y sus estrategias declaradas en el manifiesto."""
    normalized_format = format_param.casefold().strip()
    if normalized_format not in {"table", "json"}:
        sys.stderr.write("Error: --format debe ser 'table' o 'json'.\n")
        raise typer.Exit(code=1)

    records: list[dict[str, object]] = [
        {
            "id": provider_id,
            "name": definition.name,
            "strategies": [strategy.driver for strategy in definition.strategies],
            "requires_browser": definition.requires_browser,
            "datacenter_waf_sensitive": definition.datacenter_waf_sensitive,
            "recommended_limit": definition.recommended_limit,
        }
        for provider_id, definition in _PROVIDER_MANIFEST.items()
    ]
    if normalized_format == "json":
        sys.stdout.write(json.dumps(records, ensure_ascii=False, indent=2) + "\n")
        return

    headers = (
        "id",
        "name",
        "strategies",
        "requires_browser",
        "datacenter_waf_sensitive",
        "recommended_limit",
    )
    rows: list[tuple[str, ...]] = []
    for provider_id, definition in _PROVIDER_MANIFEST.items():
        rows.append(
            (
                provider_id,
                definition.name,
                ",".join(strategy.driver for strategy in definition.strategies),
                str(definition.requires_browser).lower(),
                str(definition.datacenter_waf_sensitive).lower(),
                str(definition.recommended_limit),
            )
        )
    widths = [
        max(len(header), *(len(row[index]) for row in rows))
        for index, header in enumerate(headers)
    ]
    sys.stdout.write("  ".join(header.ljust(widths[index]) for index, header in enumerate(headers)) + "\n")
    for row in rows:
        sys.stdout.write("  ".join(value.ljust(widths[index]) for index, value in enumerate(row)) + "\n")


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    url: Annotated[
        str | None,
        typer.Option("--url", "-u", help="URL de catálogo o curso; el dominio detecta el proveedor."),
    ] = None,
    provider: Annotated[
        str | None,
        typer.Option("--provider", "-p", help=f"Proveedor: {_provider_choices()}."),
    ] = None,
    output: Annotated[
        str,
        typer.Option("--output", "-o", help="Archivo CSV/JSON-LD o '-' para stdout (JSON-LD por defecto)."),
    ] = "results.csv",
    format_param: Annotated[
        str | None,
        typer.Option("--format", "-f", help="csv o jsonld; si se omite, se infiere y '-' usa jsonld por defecto."),
    ] = None,
    limit: Annotated[
        int,
        typer.Option("--limit", "-l", help="Máximo de cursos válidos; 0 no limita."),
    ] = 0,
    render: Annotated[
        bool,
        typer.Option("--render", help="Renderizado JavaScript con Playwright; NetAcad siempre lo usa."),
    ] = False,
    enable_bfs: Annotated[
        bool,
        typer.Option("--enable-bfs", help="Activar BFS para sitios sin proveedor; apagado por defecto."),
    ] = False,
    enable_modules: Annotated[
        bool,
        typer.Option("--enable-modules", help="Incluir módulos de Microsoft Learn además de learningPaths."),
    ] = False,
    max_pages: Annotated[
        int,
        typer.Option("--max-pages", help="Máximo de páginas para el rastreador BFS genérico."),
    ] = 100,
    skip_waf_sensitive: Annotated[
        bool,
        typer.Option(
            "--skip-waf-sensitive",
            help="Omitir proveedores sensibles a WAF cuando --provider all.",
        ),
    ] = False,
) -> None:
    """Punto de entrada general de Cursodex v0.5.0."""
    if ctx.invoked_subcommand is None:
        if url or provider:
            _execute_scrape(
                url=url,
                provider=provider,
                output=output,
                format_param=format_param,
                limit=limit,
                render=render,
                enable_bfs=enable_bfs,
                enable_modules=enable_modules,
                max_pages=max_pages,
                skip_waf_sensitive=skip_waf_sensitive,
            )
        else:
            sys.stderr.write(
                "Error: Debe especificar al menos una URL (--url / -u) o un proveedor (--provider / -p). "
                "Use --help para ver las opciones disponibles.\n"
            )
            emit_run_summary(
                provider=None,
                url=None,
                courses_extracted=0,
                needs_review_count=0,
                exit_code=1,
                elapsed_seconds=0.0,
            )
            raise typer.Exit(code=1)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    try:
        rc = app(standalone_mode=False)
        sys.exit(rc if isinstance(rc, int) else 0)
    except click.ClickException as exc:
        sys.stderr.write(f"Error de CLI: {exc.format_message()}\n")
        emit_run_summary(
            provider=None,
            url=None,
            courses_extracted=0,
            needs_review_count=0,
            exit_code=1,
            elapsed_seconds=0.0,
        )
        sys.exit(1)
    except typer.Exit as exc:
        sys.exit(exc.exit_code)
    except Exception as exc:
        logger.error(f"Error inesperado: {exc}", exc_info=True)
        emit_run_summary(
            provider=None,
            url=None,
            courses_extracted=0,
            needs_review_count=0,
            exit_code=1,
            elapsed_seconds=0.0,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
