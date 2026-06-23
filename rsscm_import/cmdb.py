"""CMDB reader — load current train state from export (Excel/zip) or API."""
from __future__ import annotations

from typing import Protocol

from rsscm_import.delivery import parse_delivery


class CmdbReader(Protocol):
    def read(self) -> list[dict]:
        """Return current train state as a list of normalized item dicts."""
        ...


class FileCmdbReader:
    """Reads current state from a file/zip export, via the parser registry."""

    def __init__(self, path: str):
        self.path = path

    def read(self) -> list[dict]:
        return [it.to_dict() for it in parse_delivery(self.path)]


class ApiCmdbReader:
    """Reads current state from the Django API (current baseline)."""

    def __init__(self, api_url: str):
        self.api_url = api_url

    def read(self) -> list[dict]:
        # TODO: assemble current state from /software-items/ + /software-releases/
        raise NotImplementedError("API CMDB reader not yet implemented — use a file export.")


def read_current_state(path: str) -> list[dict]:
    """Read current train state from a CMDB export (Excel/zip)."""
    return FileCmdbReader(path).read()
