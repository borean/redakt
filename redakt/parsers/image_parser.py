from pathlib import Path

from redakt.core.entities import PIIEntity
from redakt.parsers.base import BaseParser, ParseResult


class ImageParser(BaseParser):
    """Image parser - delegates entirely to LLM vision model."""

    def extract_text(self, file_path: Path) -> ParseResult:
        return ParseResult(
            text="",
            file_path=file_path,
            metadata={"type": "image", "requires_vision": True},
        )

    def create_anonymized(
        self,
        file_path: Path,
        entities: list[PIIEntity],
        output_path: Path | None = None,
    ) -> Path:
        output_path = output_path or self.output_filename(file_path, suffix=".txt")

        lines = [
            f"# Anonymized Content - {file_path.name}",
            "",
            "## Detected PII Entities",
            "",
        ]
        for entity in entities:
            lines.append(
                f"- **{entity.placeholder}** ({entity.category}): "
                f"confidence {entity.confidence:.0%}"
            )

        lines.extend(
            [
                "",
                "## Note",
                "Original image was not modified. PII entities listed above were "
                "detected via the vision model.",
            ]
        )

        output_path.write_text("\n".join(lines), encoding="utf-8")
        return output_path
