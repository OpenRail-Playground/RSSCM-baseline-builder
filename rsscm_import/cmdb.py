"""CMDB reader — load current train state from Excel export or API."""
from pathlib import Path
from typing import Protocol

from rsscm_import.ladeliste import parse_ladeliste


class CmdbReader(Protocol):
    def read(self) -> list[dict]:
        """Return current train state as list of software items."""
        ...


class ExcelCmdbReader:
    def __init__(self, path: str):
        self.path = path

    def read(self) -> list[dict]:
        return parse_ladeliste(self.path)


class ApiCmdbReader:
    """Stub — reads current state from Django API when available."""

    def __init__(self, api_url: str):
        self.api_url = api_url

    def read(self) -> list[dict]:
        # TODO: implement when API is available
        raise NotImplementedError("API reader not yet implemented — use Excel export for now.")


def read_current_state(path: str) -> list[dict]:
    """Read current train state from CMDB export (Excel/CSV/zip)."""
    reader = ExcelCmdbReader(path)
    return reader.read()
