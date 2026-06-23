"""API client — push normalized data to Django backend."""
import json
from pathlib import Path

import httpx


class RsscmApiClient:
    """Client for the RSSCM Django REST API."""

    def __init__(self, base_url: str, dry_run: bool = False):
        self.base_url = base_url.rstrip("/")
        self.dry_run = dry_run
        self._client = None if dry_run else httpx.Client(base_url=self.base_url, timeout=30)

    def _post(self, endpoint: str, payload: dict) -> dict | None:
        if self.dry_run:
            print(f"  POST {self.base_url}/{endpoint}/")
            print(f"    {json.dumps(payload, indent=4)}")
            return {"id": -1, **payload}
        resp = self._client.post(f"/{endpoint}/", json=payload)
        resp.raise_for_status()
        return resp.json()

    def create_manufacturer(self, name: str) -> dict:
        return self._post("manufacturers", {"name": name})

    def create_component(self, name: str, component_type: str, manufacturer_id: int | None = None) -> dict:
        payload = {"name": name, "component_type": component_type}
        if manufacturer_id:
            payload["component_manufacturer"] = manufacturer_id
        return self._post("components", payload)

    def create_software_item(self, name: str, software_type: str, parent_id: int | None = None,
                             component_id: int | None = None, manufacturer_id: int | None = None) -> dict:
        payload = {"name": name, "software_type": software_type}
        if parent_id:
            payload["parent"] = parent_id
        if component_id:
            payload["component"] = component_id
        if manufacturer_id:
            payload["manufacturer"] = manufacturer_id
        return self._post("software-items", payload)

    def create_software_release(self, item_id: int, version_string: str,
                                release_archive_hash: str = "", release_archive_link: str = "",
                                sbom_reference: str = "") -> dict:
        payload = {
            "item": item_id,
            "version_string": version_string,
            "release_archive_hash": release_archive_hash,
            "release_archive_link": release_archive_link,
            "sbom_reference": sbom_reference,
        }
        return self._post("software-releases", payload)

    def close(self):
        if self._client:
            self._client.close()


def push_to_backend(clean_items: list[dict], api_url: str, dry_run: bool = False):
    """Push a clean baseline (NEW + UPDATED items) to the Django backend."""
    client = RsscmApiClient(api_url, dry_run=dry_run)

    if not clean_items:
        print("  Nothing to push (no NEW or UPDATED items).")
        return

    print(f"  Pushing {len(clean_items)} items to {api_url}...")

    for item in clean_items:
        # Create SoftwareItem
        sw_item = client.create_software_item(
            name=item.get("name", ""),
            software_type=item.get("software_type", "Other"),
        )
        # Create SoftwareRelease
        client.create_software_release(
            item_id=sw_item["id"],
            version_string=item.get("version", ""),
            release_archive_hash=item.get("sha256", ""),
            release_archive_link=item.get("release_archive_link", ""),
        )

    print(f"  ✓ {len(clean_items)} items pushed.")
    client.close()
