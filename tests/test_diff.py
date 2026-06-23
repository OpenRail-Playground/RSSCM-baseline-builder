"""Tests for diff engine."""
from rsscm_import.diff import compute_diff


def test_new_items():
    delivery = [{"subsystem": "A", "system_component": "B", "name": "SW1", "file_artifact": "f.bin", "version": "1.0"}]
    current = []
    result = compute_diff(delivery, current)
    assert len(result) == 1
    assert result[0]["status"] == "NEW"


def test_updated_items():
    delivery = [{"subsystem": "A", "system_component": "B", "name": "SW1", "file_artifact": "f.bin", "version": "2.0"}]
    current = [{"subsystem": "A", "system_component": "B", "name": "SW1", "file_artifact": "f.bin", "version": "1.0"}]
    result = compute_diff(delivery, current)
    assert len(result) == 1
    assert result[0]["status"] == "UPDATED"
    assert result[0]["previous_version"] == "1.0"


def test_unchanged_items():
    delivery = [{"subsystem": "A", "system_component": "B", "name": "SW1", "file_artifact": "f.bin", "version": "1.0"}]
    current = [{"subsystem": "A", "system_component": "B", "name": "SW1", "file_artifact": "f.bin", "version": "1.0"}]
    result = compute_diff(delivery, current)
    assert len(result) == 1
    assert result[0]["status"] == "UNCHANGED"


def test_mixed_diff():
    delivery = [
        {"subsystem": "A", "system_component": "B", "name": "SW1", "file_artifact": "f1.bin", "version": "1.0"},
        {"subsystem": "A", "system_component": "B", "name": "SW2", "file_artifact": "f2.bin", "version": "3.0"},
        {"subsystem": "A", "system_component": "C", "name": "SW3", "file_artifact": "f3.bin", "version": "1.0"},
    ]
    current = [
        {"subsystem": "A", "system_component": "B", "name": "SW1", "file_artifact": "f1.bin", "version": "1.0"},
        {"subsystem": "A", "system_component": "B", "name": "SW2", "file_artifact": "f2.bin", "version": "2.0"},
    ]
    result = compute_diff(delivery, current)
    statuses = {r["name"]: r["status"] for r in result}
    assert statuses["SW1"] == "UNCHANGED"
    assert statuses["SW2"] == "UPDATED"
    assert statuses["SW3"] == "NEW"


def test_real_data_diff():
    """Integration test with real fixture data."""
    from pathlib import Path
    from rsscm_import.ladeliste import parse_ladeliste
    from rsscm_import.cmdb import read_current_state

    fixtures = Path(__file__).parent / "fixtures"
    delivery = parse_ladeliste(str(fixtures / "Chaos_HackTrain_Ladeliste.zip"))
    current = read_current_state(str(fixtures / "Train_Asset_Baseline_Hacktrain.xlsx"))
    result = compute_diff(delivery, current)

    updated = [r for r in result if r["status"] == "UPDATED"]
    unchanged = [r for r in result if r["status"] == "UNCHANGED"]

    assert len(updated) > 0, "Expected some UPDATED items (Ladeliste has version bumps)"
    assert len(unchanged) > 0, "Expected some UNCHANGED items"
    assert len(updated) + len(unchanged) == len(result)  # No NEW in this test data
