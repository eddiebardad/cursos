from abc import ABC, abstractmethod
from collections.abc import Iterable

from schemas.models import Course


class BaseExporter(ABC):
    @abstractmethod
    def export(self, courses: Iterable[Course], destination: str) -> None:
        pass
