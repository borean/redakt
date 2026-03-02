from pathlib import Path

from redakt.parsers.base import BaseParser
from redakt.parsers.docx_parser import DocxParser
from redakt.parsers.excel_parser import ExcelParser
from redakt.parsers.image_parser import ImageParser
from redakt.parsers.pdf_parser import PdfParser

_PARSER_MAP: dict[str, type[BaseParser]] = {
    ".docx": DocxParser,
    ".pdf": PdfParser,
    ".xlsx": ExcelParser,
    ".png": ImageParser,
    ".jpg": ImageParser,
    ".jpeg": ImageParser,
    ".bmp": ImageParser,
    ".tiff": ImageParser,
}


def get_parser(file_path: Path) -> BaseParser:
    """Return the appropriate parser for a given file type."""
    suffix = file_path.suffix.lower()
    parser_cls = _PARSER_MAP.get(suffix)
    if parser_cls is None:
        raise ValueError(f"Unsupported file type: {suffix}")
    return parser_cls()
