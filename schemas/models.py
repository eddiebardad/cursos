import os
import sys
from pathlib import Path

from .loader import build_dynamic_model


def _resolve_rdf_path() -> str:
    """Locate the bundled RDF schema file in both normal and frozen builds."""
    candidates = []
    local_path = Path(__file__).resolve().parent / "course_schema.rdf"
    candidates.append(local_path)

    if getattr(sys, "frozen", False):
        meipass_path = Path(getattr(sys, "_MEIPASS", ""))
        if meipass_path:
            candidates.append(meipass_path / "schemas" / "course_schema.rdf")
        if getattr(sys, "executable", None):
            candidates.append(Path(sys.executable).resolve().parent / "schemas" / "course_schema.rdf")

    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    return str(local_path)


_rdf_path = _resolve_rdf_path()

# Dynamically generate the Course model from the RDF file
Course = build_dynamic_model(_rdf_path, class_uri="http://schema.org/Course")

# We can monkey-patch the to_jsonld method onto the dynamic class since it's a specific exporter requirement
def _to_jsonld(self) -> dict:
    """Serializes the model into a valid JSON-LD dictionary."""
    data = self.model_dump(by_alias=True)
    data["@context"] = {
        "schema": "https://schema.org/",
        "dcterms": "http://purl.org/dc/terms/"
    }
    data["@type"] = "schema:Course"
    return data

Course.to_jsonld = _to_jsonld
