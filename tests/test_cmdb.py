"""Tests for CMDB reader."""
from pathlib import Path
from rsscm_import.cmdb import read_current_state, ExcelCmdbReader, ApiCmdbReader
import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def test_read_current_state_excel():
    items = read_current_state(str(FIXTURES / "Train_Asset_Baseline_Hacktrain.xlsx"))
    assert len(items) > 50  # We expect ~130 items
    item = items[0]
    assert "subsystem" in item
    assert "name" in item
    assert "version" in item


def test_cmdb_contains_hvac():
    items = read_current_state(str(FIXTURES / "Train_Asset_Baseline_Hacktrain.xlsx"))
    hvac = [i for i in items if "HVAC" in i.get("subsystem", "")]
    assert len(hvac) > 0


def test_api_reader_not_implemented():
    reader = ApiCmdbReader("http://localhost:8000/api/")
    with pytest.raises(NotImplementedError):
        reader.read()
