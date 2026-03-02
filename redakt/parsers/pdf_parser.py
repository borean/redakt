from pathlib import Path

import fitz

from redakt.core.entities import PIIEntity
from redakt.parsers.base import BaseParser, ParseResult


class PdfParser(BaseParser):

    def extract_text(self, file_path: Path) -> ParseResult:
        doc = fitz.open(str(file_path))
        pages_text: list[str] = []
        needs_ocr = False

        for page_num, page in enumerate(doc):
            text = page.get_text("text")
            if text.strip():
                pages_text.append(text)
            else:
                needs_ocr = True
                try:
                    tp = page.get_textpage_ocr(language="tur+eng", dpi=300)
                    ocr_text = page.get_text("text", textpage=tp)
                    pages_text.append(ocr_text)
                except Exception:
                    pages_text.append(f"[OCR failed for page {page_num + 1}]")

        doc.close()
        full_text = "\n\n".join(pages_text)
        return ParseResult(
            text=full_text,
            file_path=file_path,
            metadata={"pages": len(pages_text), "ocr_used": needs_ocr},
        )

    def create_anonymized(
        self,
        file_path: Path,
        entities: list[PIIEntity],
        output_path: Path | None = None,
    ) -> Path:
        output_path = output_path or self.output_filename(file_path)
        doc = fitz.open(str(file_path))

        # Sort entities by length descending
        sorted_entities = sorted(entities, key=lambda e: len(e.original), reverse=True)

        for page in doc:
            for entity in sorted_entities:
                text_instances = page.search_for(entity.original)
                for inst in text_instances:
                    page.add_redact_annot(
                        inst,
                        text=entity.placeholder,
                        fontsize=9,
                        fill=(1, 1, 1),
                    )
            page.apply_redactions()

        # Scrub PDF metadata that might contain PII
        doc.set_metadata({})
        doc.save(str(output_path))
        doc.close()
        return output_path
