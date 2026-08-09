import csv
from typing import Iterable
from exporters.base import BaseExporter
from schemas.models import Course
from utils.logger import get_logger

logger = get_logger(__name__)

class CSVExporter(BaseExporter):
    def export(self, courses: Iterable[Course], destination: str) -> None:
        if not courses:
            logger.warning("No courses to export.")
            return

        iterator = iter(courses)
        try:
            first_course = next(iterator)
        except StopIteration:
            logger.warning("No courses to export.")
            return

        # Use the alias if present, otherwise the original field name
        fieldnames = [field.alias or name for name, field in Course.model_fields.items()]
        
        with open(destination, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            # Helper to write rows while converting lists to comma-separated strings
            def write_course(course: Course):
                dump = course.model_dump(by_alias=True)
                for key, val in dump.items():
                    if isinstance(val, list):
                        dump[key] = ", ".join(map(str, val))
                writer.writerow(dump)

            # Write the first course
            write_course(first_course)
            
            # Write the rest
            count = 1
            for course in iterator:
                write_course(course)
                count += 1
                
        logger.info(f"Exported {count} courses to {destination}")
