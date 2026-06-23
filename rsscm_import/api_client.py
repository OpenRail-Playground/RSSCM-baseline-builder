"""API client — push normalized data to the Django (django-ninja) backend.

Matches the contract in RSSCM/rsscm/software/api.py, mounted at /api/v1/:
  POST /manufacturers/      {name}
  POST /components/         {name, component_type, component_manufacturer_id?}
  POST /software-items/     {name, software_type, parent_id?, component_id?, manufacturer_id?, ...}
  POST /software-releases/  {version_string, item_id, release_archive_link?, release_archive_hash?, sbom_reference?, parent_ids?}
"""
from __future__ import annotations

import json

import httpx

# Component.ComponentType choices (must match the backend)
COMPONENT_TYPE_DEFAULT = "Subsystem/Grouping Category"


class RsscmApiClient:
    """Client for the RSSCM django-ninja API."""

    def __init__(self, base_url: str = "http://localhost:8000/api/v1/", dry_run: bool = False):
        self.base_url = base_url.rstrip("/")
        self.dry_run = dry_run
        self._client = None if dry_run else httpx.Client(base_url=self.base_url, timeout=30)
        # name -> id caches to avoid duplicate creates within a run
        self._manufacturers: dict[str, int] = {}
        self._components: dict[str, int] = {}
        self._fake_id = 0

    def _post(self, endpoint: str, payload: dict) -> dict:
        if self.dry_run:
            self._fake_id -= 1
            print(f"  POST {self.base_url}/{endpoint}/")
            print(f"    {json.dumps(payload)}")
            return {"id": self._fake_id, **payload}
        resp = self._client.post(f"/{endpoint}/", json=payload)
        resp.raise_for_status()
        return resp.json()

    # -- entity helpers ----------------------------------------------------- #
    def ensure_manufacturer(self, name: str) -> int | None:
        if not name:
            return None
        if name not in self._manufacturers:
            obj = self._post("manufacturers", {"name": name})
            self._manufacturers[name] = obj["id"]
        return self._manufacturers[name]

    def ensure_component(self, name: str, component_type: str = COMPONENT_TYPE_DEFAULT,
                         manufacturer_id: int | None = None) -> int | None:
        if not name:
            return None
        if name not in self._components:
            payload = {"name": name, "component_type": component_type}
            if manufacturer_id is not None:
                payload["component_manufacturer_id"] = manufacturer_id
            obj = self._post("components", payload)
            self._components[name] = obj["id"]
        return self._components[name]

    def create_software_item(self, name: str, software_type: str, parent_id: int | None = None,
                             component_id: int | None = None, manufacturer_id: int | None = None) -> dict:
        payload = {"name": name, "software_type": software_type}
        if parent_id is not None:
            payload["parent_id"] = parent_id
        if component_id is not None:
            payload["component_id"] = component_id
        if manufacturer_id is not None:
            payload["manufacturer_id"] = manufacturer_id
        return self._post("software-items", payload)

    def create_software_release(self, item_id: int, version_string: str,
                                release_archive_hash: str = "", release_archive_link: str = "",
                                sbom_reference: str = "") -> dict:
        payload = {
            "item_id": item_id,
            "version_string": version_string,
            "release_archive_hash": release_archive_hash or None,
            "release_archive_link": release_archive_link or None,
            "sbom_reference": sbom_reference or None,
        }
        return self._post("software-releases", payload)

    def close(self):
        if self._client:
            self._client.close()


def push_to_backend(clean_items: list[dict], api_url: str = "http://localhost:8000/api/v1/",
                    dry_run: bool = False) -> int:
    """Push a clean baseline (NEW + UPDATED items) to the Django backend.

    For each changed item we ensure its component exists, then create a
    SoftwareItem and a SoftwareRelease carrying the version + checksum + link.
    Returns the number of items pushed.
    """
    client = RsscmApiClient(api_url, dry_run=dry_run)

    if not clean_items:
        print("  Nothing to push (no NEW or UPDATED items).")
        client.close()
        return 0

    print(f"  Pushing {len(clean_items)} items to {client.base_url} ...")
    pushed = 0
    try:
        for item in clean_items:
            manufacturer_id = client.ensure_manufacturer(item.get("manufacturer", ""))
            component_id = client.ensure_component(item.get("system_component", "")) if item.get("system_component") else None
            sw_item = client.create_software_item(
                name=item.get("name", ""),
                software_type=item.get("software_type", "Other"),
                component_id=component_id,
                manufacturer_id=manufacturer_id,
            )
            client.create_software_release(
                item_id=sw_item["id"],
                version_string=item.get("version", ""),
                release_archive_hash=item.get("sha256", ""),
                release_archive_link=item.get("release_archive_link", ""),
            )
            pushed += 1
    finally:
        client.close()

    print(f"  ✓ {pushed} items pushed.")
    return pushed
