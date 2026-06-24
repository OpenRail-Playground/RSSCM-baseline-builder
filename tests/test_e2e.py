"""End-to-end test: real delivery + real current-state through the full pipeline
and into the live Django REST API, then verify the records landed.

Exercises the whole chain:
  parse delivery (xlsx/docx/pdf) -> read current state -> set-based diff ->
  push_to_backend (REAL HTTP POSTs) -> GET back and assert.

Auto-skips if the backend isn't reachable, so the suite stays green offline.
Start the backend (companion RSSCM repo):
    uv run rsscm/manage.py migrate && uv run rsscm/manage.py runserver
"""
from pathlib import Path

import httpx
import pytest

from rsscm_import.delivery import parse_delivery
from rsscm_import.cmdb import read_current_state
from rsscm_import.diff import compute_diff, summarize
from rsscm_import.api_client import push_to_backend

API_URL = "http://localhost:8000/api/v1/"
FIXTURES = Path(__file__).parent / "fixtures"
DELIVERY = FIXTURES / "Chaos_HackTrain_Ladeliste.zip"
CURRENT = FIXTURES / "Train_Asset_Baseline_Hacktrain.xlsx"

# Expected software-level changes (subsystem, software name, new version)
EXPECTED = [
    ("Air Conditioning (HVAC)", "332 Operating System Software", "V4.8 A"),
    ("Train Control", "Operating System", "V1.6E"),
    ("Video Surveillance (CCTV)", "Kernel Software", "1. G1.6 / 2.G2.8"),
]


def _server_up() -> bool:
    try:
        httpx.get(f"{API_URL}manufacturers/", timeout=2)
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _server_up(), reason="Django API not reachable at localhost:8000")


@pytest.fixture(scope="module")
def e2e_result():
    """Run the full pipeline end-to-end against the live API once."""
    delivery = [i.to_dict() for i in parse_delivery(str(DELIVERY))]
    current = read_current_state(str(CURRENT))
    diff = compute_diff(delivery, current)
    summary = summarize(diff)
    software_changes = [c for c in summary["changes"] if c["level"] == "Software"]
    pushed = push_to_backend(software_changes, api_url=API_URL, dry_run=False)
    return {"summary": summary, "software_changes": software_changes, "pushed": pushed}


def test_pipeline_produces_expected_diff(e2e_result):
    s = e2e_result["summary"]
    # 5 distinct changes total (3 software + 2 subsystem), no false NEWs
    assert len(s["changes"]) == 5
    assert s["new"] == 0
    assert all(c["status"] == "UPDATED" for c in s["changes"])


def test_push_count(e2e_result):
    assert e2e_result["pushed"] == len(EXPECTED) == 3


def test_records_present_in_backend(e2e_result):
    """GET back from the live API and confirm each expected item + release."""
    items = httpx.get(f"{API_URL}software-items/", timeout=10).json()
    releases = httpx.get(f"{API_URL}software-releases/", timeout=10).json()
    components = httpx.get(f"{API_URL}components/", timeout=10).json()

    item_names = {i["name"] for i in items}
    release_versions = {r["version_string"] for r in releases}
    component_names = {c["name"] for c in components}

    for subsystem, name, version in EXPECTED:
        assert name in item_names, f"missing SoftwareItem: {name}"
        assert version in release_versions, f"missing SoftwareRelease: {version}"

    # The system components became Component records
    assert "HVAC Front Box" in component_names
    assert "Video 1C1D" in component_names


def test_release_linked_to_item(e2e_result):
    """Each expected release must be attached to its software item (FK integrity)."""
    items = httpx.get(f"{API_URL}software-items/", timeout=10).json()
    by_name = {}
    for i in items:
        by_name.setdefault(i["name"], i["id"])

    for _subsystem, name, version in EXPECTED:
        item_id = by_name[name]
        rels = httpx.get(f"{API_URL}software-releases/", params={"item_id": item_id}, timeout=10).json()
        assert any(r["version_string"] == version for r in rels), \
            f"release {version} not linked to item {name} (id={item_id})"
