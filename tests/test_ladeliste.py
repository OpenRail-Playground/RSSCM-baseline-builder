"""Tests for Ladeliste parser."""
from pathlib import Path
from rsscm_import.ladeliste import parse_ladeliste, _normalize_software_type

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_ladeliste_zip():
    items = parse_ladeliste(str(FIXTURES / "Chaos_HackTrain_Ladeliste.zip"))
    assert len(items) > 100  # We expect ~520 items
    # Check structure of first item
    item = items[0]
    assert "subsystem" in item
    assert "system_component" in item
    assert "software_type" in item
    assert "name" in item
    assert "version" in item


def test_ladeliste_contains_hvac():
    items = parse_ladeliste(str(FIXTURES / "Chaos_HackTrain_Ladeliste.zip"))
    hvac_items = [i for i in items if "HVAC" in i["subsystem"]]
    assert len(hvac_items) > 0


def test_normalize_software_type():
    assert _normalize_software_type("332 Operating System Software") == "Operating System"
    assert _normalize_software_type("Application") == "Application"
    assert _normalize_software_type("Bootloader") == "Bootloader"
    assert _normalize_software_type("Configuration Data") == "Configuration"
    assert _normalize_software_type("Random Thing") == "Other"


def test_ladeliste_has_versions():
    items = parse_ladeliste(str(FIXTURES / "Chaos_HackTrain_Ladeliste.zip"))
    # All items should have a non-empty version
    for item in items:
        assert item["version"], f"Missing version for {item['name']}"
