"""Live API tests against the running Django (django-ninja) backend.

Skipped automatically if the server is not reachable, so the suite stays green
offline. Run the backend with:
    uv run rsscm/manage.py migrate && uv run rsscm/manage.py runserver
"""
import httpx
import pytest

from rsscm_import.api_client import RsscmApiClient, push_to_backend

API_URL = "http://localhost:8000/api/v1/"


def _server_up() -> bool:
    try:
        httpx.get(f"{API_URL}manufacturers/", timeout=2)
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _server_up(), reason="Django API not reachable at localhost:8000")


def test_manufacturer_roundtrip():
    client = RsscmApiClient(API_URL)
    try:
        mid = client.ensure_manufacturer("PyTest Vendor")
        assert isinstance(mid, int) and mid > 0
        # GET it back
        resp = httpx.get(f"{API_URL}manufacturers/{mid}", timeout=5)
        assert resp.status_code == 200
        assert resp.json()["name"] == "PyTest Vendor"
    finally:
        client.close()


def test_software_item_and_release_roundtrip():
    client = RsscmApiClient(API_URL)
    try:
        comp_id = client.ensure_component("PyTest Front Box")
        assert isinstance(comp_id, int)
        item = client.create_software_item(
            name="PyTest OS", software_type="Operating System", component_id=comp_id
        )
        assert item["id"] > 0
        rel = client.create_software_release(
            item_id=item["id"], version_string="V9.9 A",
            release_archive_hash="abc123", release_archive_link="file:///tmp/x.bin",
        )
        assert rel["version_string"] == "V9.9 A"
        # Verify the release is listed for the item
        resp = httpx.get(f"{API_URL}software-releases/", params={"item_id": item["id"]}, timeout=5)
        assert resp.status_code == 200
        assert any(r["version_string"] == "V9.9 A" for r in resp.json())
    finally:
        client.close()


def test_push_clean_baseline_live():
    """Push a small clean baseline through the real API and verify it lands."""
    changes = [
        {"name": "Live Push OS", "software_type": "Operating System",
         "version": "V1.6E", "system_component": "MRB4", "subsystem": "Train Control"},
    ]
    pushed = push_to_backend(changes, api_url=API_URL, dry_run=False)
    assert pushed == 1

    resp = httpx.get(f"{API_URL}software-items/", params={"software_type": "Operating System"}, timeout=5)
    assert resp.status_code == 200
    assert any(i["name"] == "Live Push OS" for i in resp.json())
