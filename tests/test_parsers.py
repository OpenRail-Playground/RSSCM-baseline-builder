"""Tests for the pluggable parsers (xlsx/docx/pdf) and the registry."""
import zipfile
from pathlib import Path

import pytest

from rsscm_import.parsers import registry
from rsscm_import.parsers.base import NormalizedItem, normalize_software_type

FIXTURES = Path(__file__).parent / "fixtures"
LADELISTE = FIXTURES / "Chaos_HackTrain_Ladeliste.zip"

# File inside the delivery zip -> (parser class name, expected subsystem)
SAMPLES = {
    "Hack4Rail_2026/Train_Asset_Baseline_Hacktrain_1_AC.xlsx": ("XlsxParser", "Air Conditioning (HVAC)"),
    "Hack4Rail_2026/Train_Asset_Baseline_Hacktrain_6_Brake.docx": ("DocxParser", "Brake"),
    "Hack4Rail_2026/Train_Asset_Baseline_Hacktrain_9_WC.pdf": ("PdfParser", "Toilet (WC)"),
}


def _read(member: str) -> bytes:
    with zipfile.ZipFile(LADELISTE) as zf:
        return zf.read(member)


@pytest.mark.parametrize("member,expected", SAMPLES.items())
def test_parser_dispatch_and_parse(member, expected):
    parser_name, expected_subsystem = expected
    parser = registry.get_parser(member)
    assert type(parser).__name__ == parser_name

    items = parser.parse(_read(member), source=Path(member).name)
    assert items, f"{member} produced no items"
    assert all(isinstance(i, NormalizedItem) for i in items)

    # Every parser must emit the full tree levels
    levels = {i.level for i in items}
    assert "Software" in levels
    assert "Subsystem" in levels

    # The subsystem is correctly identified
    subsystems = {i.subsystem for i in items if i.subsystem}
    assert expected_subsystem in subsystems


def test_software_items_have_version_and_type():
    items = registry.get_parser("x.xlsx").parse(
        _read("Hack4Rail_2026/Train_Asset_Baseline_Hacktrain_1_AC.xlsx"), source="AC.xlsx"
    )
    sw = [i for i in items if i.level == "Software"]
    assert sw
    for i in sw:
        assert i.version, f"missing version: {i.name}"
        assert i.software_type in {
            "Operating System", "Application", "Configuration", "Firmware",
            "Bootloader", "Drivers", "Secrets", "Other", "Subsystem Baseline",
        }


def test_normalize_software_type():
    assert normalize_software_type("332 Operating System Software") == "Operating System"
    assert normalize_software_type("Application") == "Application"
    assert normalize_software_type("Bootloader") == "Bootloader"
    assert normalize_software_type("MVB Configuration") == "Configuration"
    assert normalize_software_type("Kernel Software") == "Firmware"
    assert normalize_software_type("Etwas Unbekanntes") == "Other"


def test_registry_unknown_extension():
    assert registry.get_parser("notes.txt") is None
