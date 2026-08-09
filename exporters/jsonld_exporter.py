import json
from typing import Iterable
from exporters.base import BaseExporter
from schemas.models import Course
from utils.logger import get_logger

logger = get_logger(__name__)

class JSONLDExporter(BaseExporter):
    def export(self, courses: Iterable[Course], destination: str) -> None:
        count = 0
        
        # Save as a JSON Array of JSON-LD objects
        jsonld_data = []
        for course in courses:
            jsonld_data.append(course.to_jsonld())
            count += 1
            
        if not count:
            logger.warning("No courses to export.")
            return
            
        with open(destination, mode='w', encoding='utf-8') as f:
            json.dump(jsonld_data, f, indent=2, ensure_ascii=False)
                
        logger.info(f"Exported {count} courses to {destination} in JSON-LD format")
