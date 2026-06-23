"""PdfParser — parse PDF deliveries into NormalizedItem list."""
from __future__ import annotations

import io

import pdfplumber

from rsscm_import.parsers.base import NormalizedItem
from rsscm_import.parsers.tree import parse_tree_rows


class PdfParser:
    """Parses .pdf deliveries by extracting tables across all pages.

    Concatenates table rows from every page (tables may span pages), then
    hands the combined grid to the shared tree normalizer. Header detection
    inside the normalizer copes with the header appearing mid-grid.
    """

    def parse(self, data: bytes, source: str) -> list[NormalizedItem]:
        all_rows: list = []
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages:
                for table in page.extract_tables() or []:
                    for row in table:
                        # Normalize None cells to empty strings
                        all_rows.append([(c or "").replace("\n", " ").strip() for c in row])

        if not all_rows:
            return []

        # The normalizer detects the header, or falls back to positional mapping
        # (PDF extraction often merges the 'Structure'+'Level' header cells).
        return parse_tree_rows(all_rows, source)
