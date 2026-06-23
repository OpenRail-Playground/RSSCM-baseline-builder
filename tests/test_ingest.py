"""Tests for vendor delivery ingestion."""
from pathlib import Path
from rsscm_import.ingest import ingest_delivery, classify_file

FIXTURES = Path(__file__).parent / "fixtures"


def test_classify_file():
    assert classify_file("firmware.hex") == "firmware"
    assert classify_file("K78M110_appl.MHX") == "firmware"
    assert classify_file("doc.pdf") == "document"
    assert classify_file("data.xlsx") == "data"
    assert classify_file("archive.zip") == "archive"
    assert classify_file("tool.exe") == "executable"
    assert classify_file("readme.txt") == "other"


def test_ingest_hvac_zip():
    result = ingest_delivery(str(FIXTURES / "HVAC_Firmware_K78M110.zip"))
    assert len(result) == 4
    types = {e["type"] for e in result}
    assert "firmware" in types
    assert "document" in types
    assert "archive" in types
    # All have sha256
    for entry in result:
        assert len(entry["sha256"]) == 64


def test_ingest_ladeliste_zip():
    result = ingest_delivery(str(FIXTURES / "Chaos_HackTrain_Ladeliste.zip"))
    assert len(result) == 12
    types = {e["type"] for e in result}
    assert "data" in types
    assert "document" in types


def test_nested_archive_detection():
    """The HVAC zip contains a nested .zip which should be detected."""
    result = ingest_delivery(str(FIXTURES / "HVAC_Firmware_K78M110.zip"))
    nested = [e for e in result if e["type"] == "archive"]
    assert len(nested) == 1
    assert "nested" in nested[0]
