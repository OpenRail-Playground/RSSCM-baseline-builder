"""Pluggable parsers — one per file type/component, all normalizing to the RSSCM standard model."""
from rsscm_import.parsers.base import (
    NormalizedItem,
    Parser,
    ParserRegistry,
    registry,
)

# Register built-in parsers
from rsscm_import.parsers.xlsx_parser import XlsxParser
from rsscm_import.parsers.docx_parser import DocxParser
from rsscm_import.parsers.pdf_parser import PdfParser

registry.register([".xlsx", ".xlsm", ".xls"], XlsxParser)
registry.register([".docx", ".doc"], DocxParser)
registry.register([".pdf"], PdfParser)

__all__ = ["NormalizedItem", "Parser", "ParserRegistry", "registry"]
