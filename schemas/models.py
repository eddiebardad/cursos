import os
from .loader import build_dynamic_model

# Resolve the path to the local RDF vocabulary file
_current_dir = os.path.dirname(os.path.abspath(__file__))
_rdf_path = os.path.join(_current_dir, "course_schema.rdf")

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
