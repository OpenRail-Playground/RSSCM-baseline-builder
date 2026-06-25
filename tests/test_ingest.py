"""Tests for vendor delivery ingestion.

The classification / SHA-256 / nested-archive (zip-bomb-guard) behaviour is
exercised with a synthetic zip built in-test, so the suite needs no real vendor
firmware sample.
"""
import zipfile
from pathlib import Path

from rsscm_import.ingest import ingest_delivery, classify_file

FIXTURES = Path(__file__).parent / "fixtures"


def _make_zip(path: Path, files: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return path


def test_classify_file():
    assert classify_file("firmware.hex") == "firmware"
    assert classify_file("appl.MHX") == "firmware"
    assert classify_file("doc.pdf") == "document"
    assert classify_file("data.xlsx") == "data"
    assert classify_file("archive.zip") == "archive"
    assert classify_file("tool.exe") == "executable"
    assert classify_file("readme.txt") == "other"


def test_ingest_classifies_and_hashes(tmp_path):
    """A delivery zip is extracted, every file classified and SHA-256 hashed."""
    inner = _make_zip(tmp_path / "inner.zip", {"module.s19": b"S0 firmware record"})
    delivery = _make_zip(tmp_path / "delivery.zip", {
        "controller_appl.hex": b"firmware bytes",
        "manual.pdf": b"%PDF-1.4 dummy",
        "inner.zip": inner.read_bytes(),
    })
    result = ingest_delivery(str(delivery))
    assert len(result) == 3
    types = {e["type"] for e in result}
    assert {"firmware", "document", "archive"} <= types
    for entry in result:
        assert len(entry["sha256"]) == 64


def test_ingest_ladeliste_zip():
    result = ingest_delivery(str(FIXTURES / "Chaos_HackTrain_Ladeliste.zip"))
    assert len(result) == 12
    types = {e["type"] for e in result}
    assert "data" in types
    assert "document" in types


def test_nested_archive_detection(tmp_path):
    """A zip nested inside the delivery is detected and recursively classified."""
    inner = _make_zip(tmp_path / "inner.zip", {"module.s19": b"S0 firmware"})
    delivery = _make_zip(tmp_path / "delivery.zip", {
        "appl.hex": b"fw",
        "inner.zip": inner.read_bytes(),
    })
    result = ingest_delivery(str(delivery))
    nested = [e for e in result if e["type"] == "archive"]
    assert len(nested) == 1
    assert "nested" in nested[0]
    assert any(e["type"] == "firmware" for e in nested[0]["nested"])
