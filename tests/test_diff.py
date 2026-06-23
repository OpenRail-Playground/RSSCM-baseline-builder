"""Tests for the set-based diff engine."""
from rsscm_import.diff import compute_diff, summarize


def _item(sub, comp, name, ver, level="Software"):
    return {"subsystem": sub, "system_component": comp, "name": name, "version": ver, "level": level}


def test_new_items():
    delivery = [_item("A", "B", "SW1", "1.0")]
    result = compute_diff(delivery, [])
    assert len(result) == 1 and result[0]["status"] == "NEW"


def test_updated_items():
    delivery = [_item("A", "B", "SW1", "2.0")]
    current = [_item("A", "B", "SW1", "1.0")]
    result = compute_diff(delivery, current)
    assert result[0]["status"] == "UPDATED"
    assert result[0]["previous_version"] == "1.0"
    assert "2.0" in result[0]["version"]


def test_unchanged_items():
    delivery = [_item("A", "B", "SW1", "1.0")]
    current = [_item("A", "B", "SW1", "1.0")]
    result = compute_diff(delivery, current)
    assert result[0]["status"] == "UNCHANGED"


def test_duplicate_instances_with_mixed_versions():
    """The same node appears twice in the delivery with different versions;
    one is new. It must be reported as a single UPDATED change (set-based)."""
    delivery = [
        _item("AC", "HVAC Front Box", "332 OS", "V4.8 A"),
        _item("AC", "HVAC Front Box", "332 OS", "V4.1 A"),  # duplicate instance, old ver
    ]
    current = [_item("AC", "HVAC Front Box", "332 OS", "V4.1 A")]
    result = compute_diff(delivery, current)
    assert len(result) == 1
    assert result[0]["status"] == "UPDATED"
    assert "V4.8 A" in result[0]["version"]


def test_whitespace_robust_matching():
    delivery = [_item("AC ", "HVAC  Front Box", "332  OS", "V4.8")]
    current = [_item("AC", "HVAC Front Box", "332 OS", "V4.1")]
    result = compute_diff(delivery, current)
    assert result[0]["status"] == "UPDATED"  # matched despite whitespace differences


def test_summarize_counts():
    delivery = [_item("A", "B", "SW1", "2.0"), _item("A", "B", "SW2", "1.0")]
    current = [_item("A", "B", "SW1", "1.0"), _item("A", "B", "SW2", "1.0")]
    s = summarize(compute_diff(delivery, current))
    assert s["updated"] == 1 and s["unchanged"] == 1 and len(s["changes"]) == 1
