"""Delivery aggregator — route every file in a delivery to its parser.

This is the heart of the "magic import pipeline": a delivery is a chaotic mix
of file formats (xlsx, docx, pdf, ...). We dispatch each file to the parser
registered for its type and aggregate the normalized items. New formats only
need a new parser registered in `parsers/__init__.py`.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

from rsscm_import.parsers import registry
from rsscm_import.parsers.base import NormalizedItem


def parse_delivery(path: str) -> list[NormalizedItem]:
    """Parse every supported file in a delivery (zip or folder)."""
    p = Path(path)
    if p.is_file() and p.suffix.lower() == ".zip":
        return _parse_zip(p)
    if p.is_dir():
        return _parse_folder(p)
    if p.is_file():
        return _parse_single(p.read_bytes(), p.name)
    raise FileNotFoundError(path)


def _parse_single(data: bytes, filename: str) -> list[NormalizedItem]:
    parser = registry.get_parser(filename)
    if parser is None:
        return []
    try:
        return parser.parse(data, source=filename)
    except Exception as exc:  # one bad file shouldn't abort the whole delivery
        print(f"  ! Failed to parse {filename}: {exc}")
        return []


def _parse_zip(zip_path: Path) -> list[NormalizedItem]:
    items: list[NormalizedItem] = []
    with zipfile.ZipFile(zip_path, "r") as zf:
        for name in zf.namelist():
            if name.endswith("/"):
                continue
            if registry.get_parser(name) is None:
                continue
            items.extend(_parse_single(zf.read(name), Path(name).name))
    return items


def _parse_folder(folder: Path) -> list[NormalizedItem]:
    items: list[NormalizedItem] = []
    for fpath in folder.rglob("*"):
        if fpath.is_file() and registry.get_parser(fpath.name) is not None:
            items.extend(_parse_single(fpath.read_bytes(), fpath.name))
    return items
