"""XlsxParser — parse Excel deliveries (tree or flat) into NormalizedItem list."""
from __future__ import annotations

import io

import openpyxl

from rsscm_import.parsers.base import NormalizedItem, normalize_software_type
from rsscm_import.parsers.tree import parse_tree_rows, _headers, _get

TREE_SHEET_CANDIDATES = ["Train Asset (Tree)", "Tree", "Baseline"]
FLAT_SHEET_CANDIDATES = ["Flat Data", "Flat", "Data"]


class XlsxParser:
    """Parses .xlsx/.xls deliveries.

    Prefers the hierarchical 'Tree' sheet (Level + Version per node); falls
    back to a 'Flat Data' sheet. Header-driven, so it tolerates column
    reordering between deliveries.
    """

    def parse(self, data: bytes, source: str) -> list[NormalizedItem]:
        wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
        try:
            sheet = self._pick_sheet(wb, TREE_SHEET_CANDIDATES)
            if sheet is not None:
                rows = list(wb[sheet].iter_rows(values_only=True))
                return parse_tree_rows(rows, source)
            sheet = self._pick_sheet(wb, FLAT_SHEET_CANDIDATES)
            if sheet is not None:
                return self._parse_flat(wb[sheet], source)
            return self._parse_flat(wb[wb.sheetnames[0]], source)
        finally:
            wb.close()

    @staticmethod
    def _pick_sheet(wb, candidates: list[str]) -> str | None:
        for name in candidates:
            if name in wb.sheetnames:
                return name
        return None

    def _parse_flat(self, ws, source: str) -> list[NormalizedItem]:
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return []
        h = _headers(rows[0])
        items: list[NormalizedItem] = []
        for row in rows[1:]:
            if not row or not any(row):
                continue
            sw_type = _get(row, h.get("software type"))
            ver = _get(row, h.get("sw version", h.get("version")))
            if not sw_type or not ver:
                continue
            items.append(NormalizedItem(
                name=sw_type,
                version=ver,
                level="Software",
                software_type=normalize_software_type(sw_type),
                subsystem=_get(row, h.get("subsystem")),
                system_component=_get(row, h.get("system component")),
                hardware=_get(row, h.get("hardware (board)", h.get("hardware"))),
                part_number=_get(row, h.get("part number")),
                file_artifact=_get(row, h.get("file / artifact", h.get("file/artifact"))),
                release=_get(row, h.get("release")),
                tool=_get(row, h.get("tool")),
                source_file=source,
            ))
        return items
