"""Integration test: real delivery vs real CMDB -> expected standardized changes.

This encodes the 'expected baseline output' the team reconciled against a
domain expert's manual change list. It doubles as a regression guard for the
whole pipeline (parsers -> normalize -> diff).
"""
from pathlib import Path

import pytest

from rsscm_import.delivery import parse_delivery
from rsscm_import.cmdb import read_current_state
from rsscm_import.diff import compute_diff, summarize

FIXTURES = Path(__file__).parent / "fixtures"
DELIVERY = FIXTURES / "Chaos_HackTrain_Ladeliste.zip"
CMDB = FIXTURES / "Train_Asset_Baseline_Hacktrain.xlsx"


@pytest.fixture(scope="module")
def changes():
    delivery = [i.to_dict() for i in parse_delivery(str(DELIVERY))]
    current = read_current_state(str(CMDB))
    result = compute_diff(delivery, current)
    return summarize(result)["changes"]


def _find(changes, subsystem_substr, name_substr):
    for c in changes:
        if subsystem_substr in c["subsystem"] and name_substr in c["name"]:
            return c
    return None


def test_all_formats_contribute(changes):
    """Changes must come from xlsx, docx and pdf sources combined."""
    # parse the whole delivery and confirm every format yielded items
    items = [i.to_dict() for i in parse_delivery(str(DELIVERY))]
    sources = {i["source_file"].rsplit(".", 1)[-1].lower() for i in items}
    assert {"xlsx", "docx", "pdf"} <= sources


def test_expected_changes_present(changes):
    # AC: 332 Operating System Software V4.1 A -> V4.8 A  (colleague item 1)
    ac = _find(changes, "Air Conditioning", "332 Operating System")
    assert ac and ac["status"] == "UPDATED" and "V4.8 A" in ac["version"]

    # Train Control: Operating System V1.5E -> V1.6E  (colleague item 4)
    tc = _find(changes, "Train Control", "Operating System")
    assert tc and "V1.6E" in tc["version"] and "V1.5E" in tc["previous_version"]

    # Toilet (WC) subsystem 9.0 -> 9.2  (colleague item 9)
    wc = _find(changes, "Toilet (WC)", "Toilet (WC)")
    assert wc and "9.2" in wc["version"]

    # RDA 12.0 -> 12.5  (the one the colleague forgot, item 12)
    rda = _find(changes, "Remote Data Transmission", "Remote Data Transmission")
    assert rda and "12.5" in rda["version"]


def test_brake_unchanged(changes):
    """Colleague item 6: Brake has no change (regression guard for the old
    false-positive that reported Brake Application C20 -> V1.27)."""
    brake = _find(changes, "Brake", "Application")
    assert brake is None


def test_train_radio_unchanged(changes):
    """Colleague item 10: Train Radio has no change. Regression guard for the
    PDF whitespace artifact ('..._20XX- XX-XX.msi') that produced a false NEW."""
    assert not any("Train Radio" in c["subsystem"] for c in changes)


def test_no_false_new(changes):
    """For this delivery/CMDB pair every real change is a version bump; a NEW
    would signal a node-identity mismatch (parser/whitespace artifact)."""
    assert all(c["status"] == "UPDATED" for c in changes)


def test_change_count_is_small(changes):
    """The clean baseline should be a handful of changes, not dozens of
    duplicate rows (deduplicated, set-based diff)."""
    assert 1 <= len(changes) <= 12
