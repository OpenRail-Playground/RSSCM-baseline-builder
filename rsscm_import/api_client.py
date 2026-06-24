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
        self._vehicle_types: dict[str, int] = {}
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

    def ensure_vehicle_type(self, name: str, evn_scheme: str | None = None) -> int | None:
        if not name:
            return None
        if name not in self._vehicle_types:
            payload = {"name": name}
            if evn_scheme:
                payload["evn_scheme"] = evn_scheme
            obj = self._post("vehicle-types", payload)
            self._vehicle_types[name] = obj["id"]
        return self._vehicle_types[name]

    def create_software_item(self, name: str, software_type: str, parent_id: int | None = None,
                             component_id: int | None = None, manufacturer_id: int | None = None,
                             vehicle_type_id: int | None = None) -> dict:
        payload = {"name": name, "software_type": software_type}
        if parent_id is not None:
            payload["parent_id"] = parent_id
        if component_id is not None:
            payload["component_id"] = component_id
        if manufacturer_id is not None:
            payload["manufacturer_id"] = manufacturer_id
        if vehicle_type_id is not None:
            payload["vehicle_type_id"] = vehicle_type_id
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


# Tree levels we seed as SoftwareItems, with their RSSCM software_type
SEED_LEVELS = {
    "Train baseline": "Train Baseline",
    "Subsystem": "Subsystem Baseline",
    "Software": None,  # use the item's own normalized software_type
}


def _group_key(item: dict) -> tuple:
    return (
        item.get("subsystem", "").strip(),
        item.get("system_component", "").strip(),
        item.get("level", "").strip(),
        item.get("name", "").strip(),
    )


def populate_full_baseline(current_items: list[dict], changes: list[dict],
                           vehicle_type_name: str, api_url: str = "http://localhost:8000/api/v1/",
                           dry_run: bool = False) -> dict:
    """Seed the full current train baseline as a VehicleType (Train X), then
    apply the delivery's changes as additional releases on the matching items.

    After this runs the backend holds the realistic current configuration of the
    train plus the proposed updates, so it can be queried (per train, per
    component, or "what needs updating").
    """
    client = RsscmApiClient(api_url, dry_run=dry_run)
    vt_id = client.ensure_vehicle_type(vehicle_type_name)

    # 1. group current items by node identity -> distinct current versions
    groups: dict[tuple, dict] = {}
    for it in current_items:
        if it.get("level", "") not in SEED_LEVELS:
            continue
        g = groups.setdefault(_group_key(it), {"versions": [], "sample": it})
        v = (it.get("version", "") or "").strip()
        if v and v not in g["versions"]:
            g["versions"].append(v)

    # 2. seed items + ONE current release each, remembering item ids + version.
    #    (The source can list the same item at different versions across car
    #    instances/variants; for a single train baseline we take one current
    #    version, so a later delivery version shows up cleanly as "needs update".)
    item_ids: dict[tuple, int] = {}
    seeded_version: dict[tuple, str] = {}
    print(f"  Seeding {len(groups)} baseline items for vehicle type '{vehicle_type_name}' ...")
    for key, g in groups.items():
        subsystem, system_component, level, name = key
        current_version = g["versions"][0] if g["versions"] else ""
        # Skip malformed version-less software rows (not valid baseline entries)
        if level == "Software" and not current_version:
            continue
        sample = g["sample"]
        software_type = SEED_LEVELS[level] or sample.get("software_type", "Other")
        component_id = client.ensure_component(system_component) if system_component else None
        item = client.create_software_item(
            name=name, software_type=software_type,
            component_id=component_id, vehicle_type_id=vt_id,
        )
        item_ids[key] = item["id"]
        seeded_version[key] = current_version
        if current_version:
            client.create_software_release(item_id=item["id"], version_string=current_version)

    # 3. apply delivery changes as new releases on the matching items (only when
    #    the delivered version differs from the currently installed one)
    applied = 0
    for ch in changes:
        if ch.get("level", "") not in SEED_LEVELS:
            continue
        key = _group_key(ch)
        introduced = ch.get("introduced") or ([ch.get("version", "")] if ch.get("version") else [])
        target = item_ids.get(key)
        if target is None:  # genuinely new item not in current baseline
            software_type = SEED_LEVELS[ch["level"]] or ch.get("software_type", "Other")
            component_id = client.ensure_component(ch.get("system_component", "")) if ch.get("system_component") else None
            obj = client.create_software_item(
                name=ch.get("name", ""), software_type=software_type,
                component_id=component_id, vehicle_type_id=vt_id,
            )
            target = obj["id"]
            item_ids[key] = target
            seeded_version[key] = ""
        for version in introduced:
            if version and version != seeded_version.get(key):
                client.create_software_release(item_id=target, version_string=version)
                applied += 1

    client.close()
    stats = {"vehicle_type_id": vt_id, "seeded_items": len(groups), "updates_applied": applied}
    print(f"  ✓ Seeded {stats['seeded_items']} items; applied {stats['updates_applied']} update release(s).")
    return stats
