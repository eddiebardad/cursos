"""
tests/test_exporters_and_cli.py
==============================================================================
Suite exhaustiva de pruebas para:
1. JSONLDExporter (compatibilidad Omeka S v4+, OAI-PMH, propiedades privadas, stdout).
2. CSVExporter (UTF-8 sin BOM, separador ';', cabeceras canónicas, stdout).
3. cli.py (contrato Unix stdout/stderr, códigos de salida 0/1/2, límites y flags).
==============================================================================
"""

import io
import json
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cli import app
from exporters.csv_exporter import CSVExporter
from exporters.jsonld_exporter import JSONLDExporter
from providers import get_provider_by_name
from providers.base import ProviderBase
from schemas.models import AccessType, Course

runner = CliRunner()


def _create_sample_courses() -> list[Course]:
    return [
        Course(
            name="Programación en Python Avanzado",
            url="https://ejemplo.com/cursos/python-avanzado",
            provider="Universidad Virtual",
            authors=["Dra. Elena Gómez", "Ing. Carlos Ruiz"],
            description="Curso intensivo con diseño de arquitecturas escalables y pruebas unitarias.",
            in_language="es",
            category="Programación y Desarrollo de Software",
            keywords=["Python", "FastAPI", "Testing"],
            access_type=AccessType.free_with_certificate,
            educational_level="Avanzado",
            time_required="PT20H",
            course_prerequisites=["Fundamentos de Python", "Bases de datos relacionales"],
            image="https://ejemplo.com/img/python.jpg",
        ),
        Course(
            name="Cloud Computing Básico",
            url="https://ejemplo.com/cursos/cloud-intro",
            provider="Cloud Academy",
            description="Fundamentos de infraestructura en la nube sin prerrequisitos previos.",
            in_language=None,  # Para comprobar que NO genera @language: null
            access_type=AccessType.free_no_certificate,
        ),
    ]


# ==============================================================================
# 1. Pruebas de JSONLDExporter
# ==============================================================================
def test_jsonld_exporter_file(tmp_path: Path):
    courses = _create_sample_courses()
    dest = tmp_path / "output.jsonld"

    exporter = JSONLDExporter()
    exporter.export(courses, str(dest))

    assert dest.exists()
    content = dest.read_text(encoding="utf-8")
    data = json.loads(content)

    assert isinstance(data, list)
    assert len(data) == 2

    c1 = data[0]
    # Validación raíz Omeka S v4+
    assert c1["@type"] == ["o:Item", "schema:Course"]
    assert c1["o:is_public"] is False

    # Cada propiedad RDF debe incluir property_id: "auto"
    assert c1["schema:name"][0]["property_id"] == "auto"
    assert c1["schema:name"][0]["@value"] == "Programación en Python Avanzado"
    assert c1["schema:name"][0]["@language"] == "es"

    # URIs
    assert c1["schema:url"][0]["type"] == "uri"
    assert c1["schema:url"][0]["@id"] == "https://ejemplo.com/cursos/python-avanzado"
    assert c1["schema:image"][0]["type"] == "uri"
    assert c1["schema:image"][0]["@id"] == "https://ejemplo.com/img/python.jpg"

    # Propiedades privadas de Omeka S
    assert c1["schema:identifier"][0]["is_public"] is False
    assert c1["schema:identifier"][0]["@value"].startswith("urn:cursodex:sha256:")
    assert c1["schema:dateModified"][0]["is_public"] is False

    # Espejo Dublin Core
    assert c1["dcterms:title"][0]["@value"] == "Programación en Python Avanzado"
    assert c1["dcterms:identifier"][0]["@value"] == "https://ejemplo.com/cursos/python-avanzado"
    assert c1["dcterms:publisher"][0]["@value"] == "Universidad Virtual"
    assert len(c1["dcterms:creator"]) == 2

    # Metadatos privados para n8n
    meta = c1["_cursodex_meta"]
    assert meta["canonical_url"] == "https://ejemplo.com/cursos/python-avanzado"
    assert meta["access_type"] == "free_with_certificate"
    assert meta["needs_review"] is False

    # Curso 2 sin idioma: NO debe existir "@language": null en ningún punto
    c2 = data[1]
    raw_c2 = json.dumps(c2)
    assert '"@language": null' not in raw_c2
    assert "inLanguage" not in c2


def test_jsonld_exporter_stdout(monkeypatch):
    courses = _create_sample_courses()
    fake_stdout = io.StringIO()
    monkeypatch.setattr("sys.stdout", fake_stdout)

    exporter = JSONLDExporter()
    exporter.export(courses, "-")

    output = fake_stdout.getvalue()
    data = json.loads(output)
    assert len(data) == 2


def test_jsonld_exporter_empty_stdout(monkeypatch):
    fake_stdout = io.StringIO()
    monkeypatch.setattr("sys.stdout", fake_stdout)

    exporter = JSONLDExporter()
    exporter.export([], "-")

    output = fake_stdout.getvalue()
    assert output == "[]\n"


# ==============================================================================
# 2. Pruebas de CSVExporter
# ==============================================================================
def test_csv_exporter_file(tmp_path: Path):
    courses = _create_sample_courses()
    dest = tmp_path / "output.csv"

    exporter = CSVExporter()
    exporter.export(courses, str(dest))

    assert dest.exists()
    raw_bytes = dest.read_bytes()
    # Confirmar ausencia de BOM UTF-8 (\ufeff)
    assert not raw_bytes.startswith(b"\xef\xbb\xbf")

    content = dest.read_text(encoding="utf-8")
    lines = [ln for ln in content.split("\n") if ln.strip()]

    # Cabeceras
    header = lines[0]
    assert "dcterms:title" in header
    assert "dcterms:identifier" in header
    assert "dcterms:creator" in header
    assert "schema:author" in header
    assert "schema:image" in header
    assert "canonical_url" in header
    assert "content_hash" in header

    # Fila 1: lista separada por ';' sin espacios
    row1 = lines[1]
    assert "Dra. Elena Gómez;Ing. Carlos Ruiz" in row1
    assert "Python;FastAPI;Testing" in row1
    assert "https://ejemplo.com/cursos/python-avanzado" in row1


def test_csv_exporter_stdout(monkeypatch):
    courses = _create_sample_courses()
    fake_stdout = io.StringIO()
    monkeypatch.setattr("sys.stdout", fake_stdout)

    exporter = CSVExporter()
    exporter.export(courses, "-")

    output = fake_stdout.getvalue()
    assert "dcterms:title" in output
    assert "Programación en Python Avanzado" in output


# ==============================================================================
# 3. Pruebas de cli.py (Contrato Unix y Códigos de Salida)
# ==============================================================================
class MockSampleProvider(ProviderBase):
    provider_name = "MockSample"
    default_url = "https://mock.example.com/catalog"

    @classmethod
    def can_handle(cls, url: str) -> bool:
        return "mock.example.com" in url

    def scrape(
        self,
        url: str,
        render: bool = False,
        limit: int = 0,
        enable_modules: bool = False,
    ) -> Iterator[Course]:
        courses = _create_sample_courses()
        yield from courses


class MockEmptyProvider(ProviderBase):
    provider_name = "MockEmpty"
    default_url = "https://empty.example.com/catalog"

    @classmethod
    def can_handle(cls, url: str) -> bool:
        return "empty.example.com" in url

    def scrape(
        self,
        url: str,
        render: bool = False,
        limit: int = 0,
        enable_modules: bool = False,
    ) -> Iterator[Course]:
        return
        yield  # generator vacío


def test_cli_output_stdout_jsonld_clean():
    """--output - sin --format debe inferir jsonld y dejar stdout 100% puro."""
    result = runner.invoke(
        app,
        ["run", "--provider", "MockSample", "--output", "-"],
    )
    assert result.exit_code == 0

    # stdout debe parsearse como JSON sin ninguna contaminación de texto
    parsed = json.loads(result.stdout)
    assert isinstance(parsed, list)
    assert len(parsed) == 2
    assert parsed[0]["schema:name"][0]["@value"] == "Programación en Python Avanzado"

    # stderr debe contener el resumen de ejecución
    assert "run_summary" in result.stderr
    assert '"exit_code": 0' in result.stderr


def test_cli_exit_code_2_when_zero_courses():
    """Código 2 cuando no hay cursos extraídos, con [] en stdout si --output -."""
    result = runner.invoke(
        app,
        ["run", "--provider", "MockEmpty", "--output", "-"],
    )
    assert result.exit_code == 2
    assert result.stdout == "[]\n"
    assert "run_summary" in result.stderr
    assert '"exit_code": 2' in result.stderr


def test_cli_exit_code_1_unknown_url_without_bfs():
    """Código 1 cuando la URL no tiene proveedor y --enable-bfs es False."""
    result = runner.invoke(
        app,
        ["run", "--url", "https://unsupported-domain.com/courses"],
    )
    assert result.exit_code == 1
    assert "crawler genérico BFS está desactivado por defecto" in result.stderr
    assert "run_summary" in result.stderr
    assert '"exit_code": 1' in result.stderr


def test_cli_limit_parameter():
    """El parámetro --limit debe recortar con precisión los resultados."""
    result = runner.invoke(
        app,
        ["run", "--provider", "MockSample", "--limit", "1", "--output", "-"],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert len(parsed) == 1


def test_cli_forwards_provider_options_and_normalizes_provider_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_options: dict[str, object] = {}

    def scrape(
        _self: MockSampleProvider,
        url: str,
        render: bool = False,
        limit: int = 0,
        enable_modules: bool = False,
    ) -> Iterator[Course]:
        captured_options.update(
            url=url,
            render=render,
            limit=limit,
            enable_modules=enable_modules,
        )
        yield from _create_sample_courses()

    monkeypatch.setattr(MockSampleProvider, "scrape", scrape)

    result = runner.invoke(
        app,
        [
            "run",
            "--provider",
            "MOCK_SAMPLE",
            "--limit",
            "1",
            "--enable-modules",
            "--output",
            "-",
        ],
    )

    assert result.exit_code == 0
    assert captured_options == {
        "url": MockSampleProvider.default_url,
        "render": False,
        "limit": 1,
        "enable_modules": True,
    }


def test_provider_name_lookup_ignores_case_spaces_and_separators() -> None:
    aprende = get_provider_by_name(" APRENDE ")
    netacad = get_provider_by_name("net_acad")

    assert aprende is not None
    assert aprende.provider_name == "Aprende"
    assert netacad is not None
    assert netacad.provider_name == "Netacad"
    assert get_provider_by_name("NETACAD") is not None


def test_cli_no_args_exits_code_1():
    """Sin URL ni Provider debe salir con código 1."""
    result = runner.invoke(app, ["run"])
    assert result.exit_code == 1
    assert "Debe especificar al menos una URL" in result.stderr


# ==============================================================================
# 4. Pruebas de Omisión de Pendiente_Categoria y Escapado en CSV
# ==============================================================================
def test_omission_of_pendiente_categoria_in_public_rdf_and_csv():
    c_unmapped = Course(
        name="Curso Esotérico Sin Categoría Mapeable",
        url="https://ejemplo.com/cursos/esoterico",
        description="Contenido que no coincide con ninguna regla del vocabulario controlado.",
        in_language="es",
    )
    assert c_unmapped.category == "Pendiente_Categoria"

    # 1. En JSON-LD
    exporter_ld = JSONLDExporter()
    buffer_ld = io.StringIO()
    import sys
    old_stdout = sys.stdout
    sys.stdout = buffer_ld
    try:
        exporter_ld.export([c_unmapped], "-")
    finally:
        sys.stdout = old_stdout

    data_ld = json.loads(buffer_ld.getvalue())[0]
    assert "schema:about" not in data_ld
    assert "dcterms:subject" not in data_ld
    # Pero sí debe conservarse en los metadatos privados para n8n
    assert data_ld["_cursodex_meta"]["category"] == "Pendiente_Categoria"

    # 2. En CSV
    exporter_csv = CSVExporter()
    buffer_csv = io.StringIO()
    sys.stdout = buffer_csv
    try:
        exporter_csv.export([c_unmapped], "-")
    finally:
        sys.stdout = old_stdout

    import csv
    reader = csv.DictReader(io.StringIO(buffer_csv.getvalue()))
    row = next(reader)
    assert row["schema:about"] == ""
    assert row["dcterms:subject"] == ""


def test_csv_semicolon_escaping_in_lists():
    c = Course(
        name="Curso con punto y coma en keywords",
        url="https://ejemplo.com/cursos/keywords-semicolon",
        description="Descripción adecuada para comprobar la sustitución de punto y coma.",
        in_language="es",
        keywords=["SQL; Bases de Datos", "Python"],
        authors=["Doe; Jane", "Smith, John"],
    )
    exporter_csv = CSVExporter()
    buffer_csv = io.StringIO()
    import sys
    old_stdout = sys.stdout
    sys.stdout = buffer_csv
    try:
        exporter_csv.export([c], "-")
    finally:
        sys.stdout = old_stdout

    import csv
    reader = csv.DictReader(io.StringIO(buffer_csv.getvalue()))
    row = next(reader)
    # Los puntos y comas internos deben haber sido convertidos a comas
    assert row["schema:keywords"] == "SQL, Bases de Datos;Python"
    assert row["schema:author"] == "Doe, Jane;Smith, John"


# ==============================================================================
# 5. Pruebas Reales de Subproceso en Sistema Operativo (Contrato Unix)
# ==============================================================================
def test_cli_subprocess_invalid_limit():
    res = subprocess.run(
        [sys.executable, "cli.py", "--limit", "invalido", "--output", "-"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert res.returncode == 1
    assert res.stdout == ""
    assert "exit_code" in res.stderr
    assert "\x1b[" not in res.stderr  # Cero secuencias ANSI de Rich


def test_cli_subprocess_unknown_flag():
    res = subprocess.run(
        [sys.executable, "cli.py", "--flag-inexistente"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert res.returncode == 1
    assert res.stdout == ""
    assert "exit_code" in res.stderr


def test_cli_subprocess_no_args():
    res = subprocess.run(
        [sys.executable, "cli.py"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert res.returncode == 1
    assert res.stdout == ""  # Exactamente 0 bytes en stdout
    assert "Debe especificar al menos una URL" in res.stderr
    assert "exit_code" in res.stderr


def test_cli_subprocess_help():
    res = subprocess.run(
        [sys.executable, "cli.py", "--help"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert res.returncode == 0
    assert "Cursodex" in res.stdout


def test_installed_console_script_help_commands_and_no_arguments() -> None:
    console_script = Path(sys.executable).with_name(
        "cursodex.exe" if os.name == "nt" else "cursodex"
    )
    assert console_script.is_file()

    top_level_help = subprocess.run(
        [str(console_script), "--help"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    run_help = subprocess.run(
        [str(console_script), "run", "--help"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    no_arguments = subprocess.run(
        [str(console_script)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert top_level_help.returncode == 0
    assert "Cursodex" in top_level_help.stdout
    assert "extracción" in top_level_help.stdout
    assert run_help.returncode == 0
    assert "run" in run_help.stdout
    assert no_arguments.returncode == 1
    assert no_arguments.stdout == ""
    assert "run_summary" in no_arguments.stderr
