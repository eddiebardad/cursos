from abc import ABC, abstractmethod
from typing import Iterable
from schemas.models import Course

class BaseExporter(ABC):
    @abstractmethod
    def export(self, courses: Iterable[Course], destination: str) -> None:
        pass
