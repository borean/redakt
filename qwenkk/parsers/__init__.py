from pathlib import Path

from qwenkk.parsers.base import BaseParser
from qwenkk.parsers.docx_parser import DocxParser
from qwenkk.parsers.excel_parser import ExcelParser
from qwenkk.parsers.image_parser import ImageParser
from qwenkk.parsers.pdf_parser import PdfParser

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
