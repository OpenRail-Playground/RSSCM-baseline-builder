"""Read-back queries against the RSSCM backend — for the demo / pitch.

Answers the practical questions:
  - "What is the software baseline of Train X?"
  - "What on Train X needs updating?" (items with more than one release version)
  - "What software runs on subcomponent Y?"
"""
from __future__ import annotations

from collections import defaultdict

import httpx


def _get(api_url: str, path: str, **params) -> list[dict]:
    with httpx.Client(base_url=api_url.rstrip("/"), timeout=15) as c:
        r = c.get(path, params=params or None)
        r.raise_for_status()
        return r.json()


def _find_by_name(rows: list[dict], name: str) -> dict | None:
    for r in rows:
        if r.get("name") == name:
            return r
    return None


def _releases_by_item(api_url: str) -> dict[int, list[str]]:
    out: dict[int, list[str]] = defaultdict(list)
    for rel in _get(api_url, "/software-releases/"):
        out[rel["item_id"]].append(rel["version_string"])
    return out


def train_baseline(api_url: str, vehicle_type_name: str) -> dict:
    """All software items for a train (vehicle type) with their version(s)."""
    vts = _get(api_url, "/vehicle-types/")
    vt = _find_by_name(vts, vehicle_type_name)
    if vt is None:
        return {"vehicle_type": vehicle_type_name, "found": False, "items": []}
    items = _get(api_url, "/software-items/", vehicle_type_id=vt["id"])
    rel = _releases_by_item(api_url)
    rows = [{"id": i["id"], "name": i["name"], "software_type": i["software_type"],
             "versions": rel.get(i["id"], [])} for i in items]
    return {"vehicle_type": vehicle_type_name, "found": True, "count": len(rows), "items": rows}


def needs_update(api_url: str, vehicle_type_name: str) -> list[dict]:
    """Items whose backend history holds more than one version — i.e. a newer
    release has arrived that isn't the one currently installed."""
    base = train_baseline(api_url, vehicle_type_name)
    out = []
    for row in base["items"]:
        versions = row["versions"]
        if len(set(versions)) > 1:
            out.append({"name": row["name"], "software_type": row["software_type"],
                        "versions": versions})
    return out


def component_software(api_url: str, component_name: str) -> dict:
    """Software running on a given (sub)component, with versions."""
    comps = _get(api_url, "/components/")
    comp = _find_by_name(comps, component_name)
    if comp is None:
        return {"component": component_name, "found": False, "items": []}
    items = _get(api_url, "/software-items/", component_id=comp["id"])
    rel = _releases_by_item(api_url)
    rows = [{"name": i["name"], "software_type": i["software_type"],
             "versions": rel.get(i["id"], [])} for i in items]
    return {"component": component_name, "found": True, "count": len(rows), "items": rows}
