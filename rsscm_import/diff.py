"""Diff engine — compute what's new/changed between delivery and current state."""


def _item_key(item: dict) -> tuple:
    """Generate a unique key for matching items between delivery and current state."""
    return (
        item.get("subsystem", "").strip(),
        item.get("system_component", "").strip(),
        item.get("name", "").strip(),
        item.get("file_artifact", "").strip(),
    )


def compute_diff(delivery_items: list[dict], current_items: list[dict]) -> list[dict]:
    """Compare delivery against current state, marking items as NEW/UPDATED/UNCHANGED."""
    current_map = {}
    for item in current_items:
        key = _item_key(item)
        current_map[key] = item

    result = []
    for item in delivery_items:
        key = _item_key(item)
        current = current_map.get(key)

        entry = {**item}
        if current is None:
            entry["status"] = "NEW"
        elif current.get("version", "").strip() != item.get("version", "").strip():
            entry["status"] = "UPDATED"
            entry["previous_version"] = current.get("version", "")
        else:
            entry["status"] = "UNCHANGED"

        result.append(entry)

    return result
