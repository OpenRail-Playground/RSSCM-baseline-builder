"""Diff engine — compute what's new/changed between delivery and current state.

Real delivery data lists the same logical node many times (one per hardware
instance / duplicate row), sometimes with *different* versions. A single-value
key with "last wins" would mask real changes. So we compare the **set of
versions** seen per node:

  - node not in current state            -> NEW
  - delivery introduces a version the
    current state does not have           -> UPDATED  (old set -> introduced)
  - otherwise                             -> UNCHANGED

This deduplicates naturally (one entry per node) and answers the operator's
real question: "which software versions does this delivery bring that aren't
on the train yet?"
"""
from __future__ import annotations

import re


def _norm(s: str) -> str:
    """Normalize a label for matching: strip + collapse internal whitespace."""
    return re.sub(r"\s+", " ", (s or "").strip())


def _as_dict(item) -> dict:
    return item.to_dict() if hasattr(item, "to_dict") else dict(item)


def _key(item: dict) -> tuple:
    """Stable identity of a node (location), independent of version."""
    return (
        _norm(item.get("subsystem", "")),
        _norm(item.get("system_component", "")),
        _norm(item.get("level", "")),
        _norm(item.get("name", "")),
    )


def _group_versions(items: list) -> dict[tuple, dict]:
    """key -> {versions: set, sample: representative item dict}."""
    out: dict[tuple, dict] = {}
    for raw in items:
        item = _as_dict(raw)
        k = _key(item)
        ver = (item.get("version", "") or "").strip()
        bucket = out.setdefault(k, {"versions": set(), "sample": item})
        if ver:
            bucket["versions"].add(ver)
    return out


def compute_diff(delivery_items: list, current_items: list) -> list[dict]:
    """Compare delivery vs current state using set-based version comparison.

    Returns one entry per delivery node, with status and (for changes) the
    introduced version(s) and the previous version(s).
    """
    current = _group_versions(current_items)
    delivery = _group_versions(delivery_items)

    result = []
    for key, dinfo in delivery.items():
        sample = dinfo["sample"]
        dvers = dinfo["versions"]
        entry = {**sample}

        if key not in current:
            entry["status"] = "NEW"
            entry["introduced"] = sorted(dvers)
            entry["version"] = "; ".join(sorted(dvers))
        else:
            cvers = current[key]["versions"]
            introduced = dvers - cvers
            if introduced:
                entry["status"] = "UPDATED"
                entry["introduced"] = sorted(introduced)
                entry["previous_version"] = "; ".join(sorted(cvers))
                entry["version"] = "; ".join(sorted(introduced))
            else:
                entry["status"] = "UNCHANGED"
                entry["version"] = "; ".join(sorted(dvers))
        result.append(entry)

    return result


def summarize(diff_result: list[dict]) -> dict:
    """Counts by status, plus the distinct changes (NEW + UPDATED)."""
    new = [r for r in diff_result if r["status"] == "NEW"]
    updated = [r for r in diff_result if r["status"] == "UPDATED"]
    unchanged = [r for r in diff_result if r["status"] == "UNCHANGED"]
    return {
        "new": len(new),
        "updated": len(updated),
        "unchanged": len(unchanged),
        "changes": new + updated,
    }
