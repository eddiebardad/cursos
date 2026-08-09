import os
import re
import rdflib
from typing import Optional, List, Union, Dict, Any, Type
from pydantic import BaseModel, Field, ConfigDict, field_validator, create_model

SCHEMA_NS = rdflib.Namespace("http://schema.org/")
DCTERMS_NS = rdflib.Namespace("http://purl.org/dc/terms/")

def map_rdf_type_to_python(range_uri: str, prop_name: str) -> Type:
    if prop_name == "keywords":
        return List[str]
    elif prop_name == "price":
        return Union[float, str]
    elif prop_name == "educationalCredentialAwarded":
        return Union[bool, str]
        
    if "Boolean" in range_uri:
        return bool
    elif "Float" in range_uri or "Number" in range_uri:
        return float
    else:
        return str

class CourseBase(BaseModel):
    """Base class for our dynamically generated model to supply config and validators."""
    model_config = ConfigDict(populate_by_name=True)

    @field_validator("timeRequired", check_fields=False)
    @classmethod
    def warn_if_invalid_duration(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            if not re.match(r"^P(?!$)(T(?=\d))?(\d+H)?(\d+M)?(\d+S)?$", v):
                from utils.logger import get_logger
                logger = get_logger(__name__)
                logger.warning(f"Invalid ISO 8601 duration format for timeRequired: {v}")
        return v

def build_dynamic_model(rdf_path: str, class_uri: str = "http://schema.org/Course") -> Type[BaseModel]:
    """
    Parses the RDF vocabulary and dynamically constructs a Pydantic model
    for the specified class URI, mapping properties and aliases.
    """
    g = rdflib.Graph()
    if not os.path.exists(rdf_path):
        raise FileNotFoundError(f"RDF schema file not found: {rdf_path}")
    g.parse(rdf_path, format="xml")
    
    fields: Dict[str, Any] = {}
    
    course_ref = rdflib.URIRef(class_uri)
    
    # Find all properties where domainIncludes is the target class
    for s, p, o in g.triples((None, SCHEMA_NS.domainIncludes, course_ref)):
        prop_str = str(s)
        prop_name = prop_str.split("/")[-1]
        
        if "schema.org" in prop_str:
            alias = f"schema:{prop_name}"
        elif "purl.org/dc/terms" in prop_str:
            alias = f"dcterms:{prop_name}"
        else:
            alias = prop_name
            
        # Get range to determine Python type
        range_uri = ""
        for rs, rp, ro in g.triples((s, SCHEMA_NS.rangeIncludes, None)):
            range_uri = str(ro)
            break
            
        py_type = map_rdf_type_to_python(range_uri, prop_name)
        
        # Hardcode name and url as required for the Course structure
        if prop_name in ["name", "url"]:
            fields[prop_name] = (py_type, Field(alias=alias))
        else:
            fields[prop_name] = (Optional[py_type], Field(default=None, alias=alias))
            
    model_name = class_uri.split("/")[-1]
    
    # Create the model using create_model
    DynamicModel = create_model(model_name, __base__=CourseBase, **fields)
    return DynamicModel
