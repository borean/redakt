from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from redakt.core.entities import PIIEntity


@dataclass
class ParseResult:
    """Result of parsing a document."""

    text: str
    file_path: Path
    metadata: dict = field(default_factory=dict)


class BaseParser(ABC):
    """Abstract base for document parsers."""

    @abstractmethod
    def extract_text(self, file_path: Path) -> ParseResult:
        ...

    @abstractmethod
    def create_anonymized(
        self,
        file_path: Path,
        entities: list[PIIEntity],
        output_path: Path | None = None,
    ) -> Path:
        """Create a new anonymized copy of the document. Returns output path."""
        ...

    @staticmethod
    def output_filename(original: Path, suffix: str | None = None) -> Path:
        stem = original.stem
        ext = suffix or original.suffix
        return original.parent / f"{stem}_anonim{ext}"
