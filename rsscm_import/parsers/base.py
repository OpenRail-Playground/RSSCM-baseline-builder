"""Base parser framework — standard data model + parser protocol + registry/dispatch."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Callable, Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Standard data model (aligned with the RSSCM Django models)
# ---------------------------------------------------------------------------

# RSSCM SoftwareItem.SoftwareType choices
SOFTWARE_TYPES = {
    "Firmware", "Configuration", "Application", "Bootloader", "Operating System",
    "Secrets", "Drivers", "Other", "Train Baseline", "Subsystem Baseline",
    "Merged Image for a complete Device",
}


@dataclass
class NormalizedItem:
    """A single node normalized to the RSSCM standard model.

    Every parser, regardless of input format (xlsx/docx/pdf/...), must emit
    these. Keys mirror the fields the diff engine and API client expect.
    """
    name: str = ""
    version: str = ""
    level: str = ""  # Train baseline | Subsystem | System component | Hardware | Software | Software component
    software_type: str = "Other"
    subsystem: str = ""
    system_component: str = ""
    hardware: str = ""
    part_number: str = ""
    file_artifact: str = ""
    release: str = ""
    tool: str = ""
    manufacturer: str = ""
    source_file: str = ""  # provenance: which file this came from

    def to_dict(self) -> dict:
        return asdict(self)

    def key(self) -> tuple:
        """Identity for diffing/dedup: where the node lives in the tree."""
        return (
            self.subsystem.strip(),
            self.system_component.strip(),
            self.hardware.strip(),
            self.level.strip(),
            self.name.strip(),
            self.file_artifact.strip(),
        )


def normalize_software_type(raw: str) -> str:
    """Map a free-text software-type string to an RSSCM SoftwareType choice."""
    lower = (raw or "").lower()
    if "operating system" in lower or "betriebssystem" in lower or lower == "os":
        return "Operating System"
    if "bootloader" in lower or "boot monitor" in lower or "boot" in lower:
        return "Bootloader"
    if "application" in lower or "appl" in lower or "anwendung" in lower:
        return "Application"
    if "config" in lower or "parameter" in lower or "konfig" in lower or "nsdb" in lower:
        return "Configuration"
    if "firmware" in lower or lower == "fw" or "kernel" in lower:
        return "Firmware"
    if "driver" in lower or "treiber" in lower:
        return "Drivers"
    if "secret" in lower or "key" in lower or "cert" in lower:
        return "Secrets"
    if "baseline" in lower:
        return "Subsystem Baseline"
    return "Other"


# ---------------------------------------------------------------------------
# Parser protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class Parser(Protocol):
    """A parser converts raw file bytes into a list of NormalizedItem."""

    def parse(self, data: bytes, source: str) -> list[NormalizedItem]:
        ...


# ---------------------------------------------------------------------------
# Registry / dispatch
# ---------------------------------------------------------------------------

class ParserRegistry:
    """Dispatch files to parsers by extension, with optional per-file overrides.

    Overrides let a specific component/file use a dedicated parser, e.g. a
    vendor whose PDFs need a bespoke reader. They are checked before the
    extension map.
    """

    def __init__(self):
        self._by_ext: dict[str, Callable[[], Parser]] = {}
        self._overrides: list[tuple[Callable[[str], bool], Callable[[], Parser]]] = []

    def register(self, extensions: list[str], parser_factory: Callable[[], Parser]) -> None:
        for ext in extensions:
            self._by_ext[ext.lower()] = parser_factory

    def register_override(self, predicate: Callable[[str], bool], parser_factory: Callable[[], Parser]) -> None:
        """Register a parser for files matching `predicate(filename) -> bool`."""
        self._overrides.append((predicate, parser_factory))

    def get_parser(self, filename: str) -> Parser | None:
        for predicate, factory in self._overrides:
            if predicate(filename):
                return factory()
        ext = Path(filename).suffix.lower()
        factory = self._by_ext.get(ext)
        return factory() if factory else None

    def supported_extensions(self) -> set[str]:
        return set(self._by_ext.keys())


# Module-level singleton registry
registry = ParserRegistry()
