"""Current train-state reader.

The second pipeline input is the *current train state* (the "Train Assets"),
which can come from different sources depending on the operator:
  - a CSV/Excel export,
  - a REST API, or
  - even a previous "Ladeliste" delivery.

Because the file/export path reuses the same parser registry as the delivery
side, a previous Ladeliste (zip of mixed files) works as a source out of the
box. The reader is pluggable so an API-backed source can be added later.
"""
from __future__ import annotations

from typing import Protocol

from rsscm_import.delivery import parse_delivery


class CurrentStateReader(Protocol):
    def read(self) -> list[dict]:
        """Return the current train state as a list of normalized item dicts."""
        ...


class FileCurrentStateReader:
    """Reads current state from a file/zip export (or a previous Ladeliste),
    via the parser registry."""

    def __init__(self, path: str):
        self.path = path

    def read(self) -> list[dict]:
        return [it.to_dict() for it in parse_delivery(self.path)]


class ApiCurrentStateReader:
    """Reads current state from the Django API (current baseline)."""

    def __init__(self, api_url: str):
        self.api_url = api_url

    def read(self) -> list[dict]:
        # TODO: assemble current state from /software-items/ + /software-releases/
        raise NotImplementedError("API current-state reader not yet implemented — use a file export.")


def read_current_state(path: str) -> list[dict]:
    """Read the current train state from a source export (Excel/CSV/zip)."""
    return FileCurrentStateReader(path).read()
