"""DocxParser — parse Word-document deliveries into NormalizedItem list."""
from __future__ import annotations

import io

from docx import Document

from rsscm_import.parsers.base import NormalizedItem
from rsscm_import.parsers.tree import looks_like_tree_header, parse_tree_rows


class DocxParser:
    """Parses .docx deliveries by finding the tree table and normalizing it.

    Vendors sometimes ship the same baseline tree embedded as a Word table.
    We scan all tables, pick the one whose header matches the tree schema,
    and hand its grid to the shared normalizer.
    """

    def parse(self, data: bytes, source: str) -> list[NormalizedItem]:
        doc = Document(io.BytesIO(data))
        best_rows: list = []

        for table in doc.tables:
            grid = [[cell.text.strip() for cell in row.cells] for row in table.rows]
            if not grid:
                continue
            # Find the tree table by its header
            if any(looks_like_tree_header(r) for r in grid[:3]):
                items = parse_tree_rows(grid, source)
                if items:
                    return items
            # Remember the largest table as a fallback
            if len(grid) > len(best_rows):
                best_rows = grid

        # Fallback: try the largest table even without a recognized header
        if best_rows:
            return parse_tree_rows(best_rows, source)
        return []
