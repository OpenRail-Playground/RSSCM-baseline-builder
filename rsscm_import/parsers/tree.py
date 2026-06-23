"""Shared tree-table normalizer.

All current delivery formats (xlsx Tree sheet, docx table, pdf table) carry the
same hierarchical table with columns: Structure, Level, Name, Version,
Part Number, HW Status, File / Artifact, Build/Flash Tool, Variants..., Remark.

Format-specific parsers extract a 2D grid (list of rows) and hand it here.
This keeps one normalization rule, header-driven so column reordering between
deliveries does not break it.
"""
from __future__ import annotations

from rsscm_import.parsers.base import NormalizedItem, normalize_software_type

TREE_LEVELS = {
    "Train baseline", "Subsystem", "System component",
    "Hardware", "Software", "Software component",
}


def _headers(row) -> dict[str, int]:
    out = {}
    for i, cell in enumerate(row):
        if cell:
            out[str(cell).strip().lower()] = i
    return out


def _get(row, idx: int | None) -> str:
    if idx is None or idx >= len(row):
        return ""
    return str(row[idx]).strip() if row[idx] is not None else ""


def looks_like_tree_header(row) -> bool:
    """True if a row looks like the tree table header."""
    labels = {str(c).strip().lower() for c in row if c}
    return "level" in labels and "name" in labels and "version" in labels


def _find_level_column(rows) -> int | None:
    """Detect which column holds the Level values (for header-less grids)."""
    best_col, best_hits = None, 0
    width = max((len(r) for r in rows), default=0)
    for col in range(width):
        hits = sum(1 for r in rows if col < len(r) and str(r[col]).strip() in TREE_LEVELS)
        if hits > best_hits:
            best_col, best_hits = col, hits
    # Require a few hits so we don't misfire on noise
    return best_col if best_hits >= 2 else None


def parse_tree_rows(rows: list, source: str) -> list[NormalizedItem]:
    """Normalize a tree-table grid (header + data rows) into NormalizedItems.

    Emits one item per node at every level, tracking hierarchy context so each
    node carries its subsystem / system_component / hardware ancestry.

    Works two ways:
    1. Header-driven (preferred): maps columns by their header labels, so column
       reordering between deliveries is tolerated.
    2. Positional fallback: when the header is missing or garbled (e.g. a PDF
       extraction merges 'Structure'+'Level'), the Level column is detected by
       its known values and remaining columns are mapped by the standard offset.
    """
    if not rows:
        return []

    # 1. Try to find a real header row in the first few rows
    header_idx = None
    for i, row in enumerate(rows[:5]):
        if row and looks_like_tree_header(row):
            header_idx = i
            break

    if header_idx is not None:
        h = _headers(rows[header_idx])
        c_level = h.get("level")
        c_name = h.get("name")
        c_ver = h.get("version")
        c_part = h.get("part number")
        c_art = h.get("file / artifact", h.get("file/artifact"))
        c_tool = h.get("build/flash tool", h.get("tool"))
        data_rows = rows[header_idx + 1:]
    else:
        # 2. Positional fallback: locate the Level column, map by standard offset
        c_level = _find_level_column(rows)
        if c_level is None:
            return []
        c_name = c_level + 1
        c_ver = c_level + 2
        c_part = c_level + 3
        c_art = c_level + 5
        c_tool = c_level + 6
        data_rows = rows

    items: list[NormalizedItem] = []
    subsystem = system_component = hardware = ""

    for row in data_rows:
        if not row or not any(row):
            continue
        level = _get(row, c_level)
        if level not in TREE_LEVELS:
            continue
        name = _get(row, c_name)
        ver = _get(row, c_ver)

        # Maintain hierarchy context
        if level == "Subsystem":
            subsystem = name
        elif level == "System component":
            system_component = name
        elif level == "Hardware":
            hardware = name

        items.append(NormalizedItem(
            name=name,
            version=ver,
            level=level,
            software_type=normalize_software_type(name) if level in ("Software", "Software component") else "Other",
            subsystem=subsystem,
            system_component=system_component if level not in ("Subsystem",) else "",
            hardware=hardware if level in ("Software", "Software component") else "",
            part_number=_get(row, c_part),
            file_artifact=_get(row, c_art),
            tool=_get(row, c_tool),
            source_file=source,
        ))

    return items
