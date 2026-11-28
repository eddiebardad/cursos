from abc import ABC, abstractmethod
from collections.abc import Iterable

from schemas.models import Course


def deduplicate_courses(courses: Iterable[Course]) -> list[Course]:
    unique: list[Course] = []
    seen_urls: set[str] = set()
    for course in courses:
        if course.canonical_url in seen_urls:
            continue
        seen_urls.add(course.canonical_url)
        unique.append(course)
    return unique


class BaseExporter(ABC):
    @abstractmethod
    def export(self, courses: Iterable[Course], destination: str) -> None:
        pass
