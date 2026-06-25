"""Transform the normalized current-state tree into the RSSCM **v2 data model**
(matching ``example/v2.json`` in the RSSCM backend):

    Train Baseline ─▶ Subsystem Baseline ─▶ System ─▶ Software

with ``Hardware/Bare Metal`` Components carrying a ``component_revision``,
release ``release_archive_link``s, and a SoftwareRelease ``parent`` chain that
mirrors the item tree.

Design decisions (see ``docs/DESIGN-v2-model.md``):

* **Train is the ROOT SoftwareItem** (``vehicle_type=None``) — a pure v2 match.
* **Two emitters.** ``to_fixture`` writes a Django ``loaddata`` fixture that is
  directly comparable to ``example/v2.json`` and is the *faithful* match — it is
  the only way to set ``component_revision``, since the ``ComponentIn`` API
  schema on ``main`` does not expose that field. ``push_via_api`` is a
  best-effort live push (revision left null).
* **Names** are derived from the source: the train and subsystem levels get a
  trailing " Baseline" (the train also has wrapping parentheses stripped, so
  "(Hacktrain)" → "Hacktrain Baseline"); system/software keep their source name,
  with internal whitespace collapsed.
* **Instance collapsing.** A system component whose name is ``<base> <digits>``
  (e.g. "HVAC Roof Unit 7024") collapses onto its base ("HVAC Roof Unit") when
  that base also exists in the same subsystem — matching v2's clean set.
* **Software dedup.** One current release per ``(subsystem, system, name)`` (the
  first/canonical instance), so a single train baseline is represented.

Source level → v2 mapping (verified against v2.json):

    Train baseline      → SoftwareItem(type="Train Baseline")      [root]
    Subsystem           → SoftwareItem(type="Subsystem Baseline")
    System component    → SoftwareItem(type="System")  + component=Hardware
    Hardware            → Component(type="Hardware/Bare Metal",
                                    component_revision=<hardware row version>)
    Software            → SoftwareItem(type=<software_type>) + component=Hardware
    Software component  → release_archive_link (the delivered file)
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

RELEASE_ASSET_BASE = "http://release-assets.example.com/"

LEVEL_TRAIN = "Train baseline"
LEVEL_SUB = "Subsystem"
LEVEL_SYS = "System component"
LEVEL_HW = "Hardware"
LEVEL_SW = "Software"
LEVEL_SWC = "Software component"

COMPONENT_TYPE_HW = "Hardware/Bare Metal"


def _clean(s: str | None) -> str:
    """Collapse internal whitespace and strip (fixes PDF/Excel artifacts)."""
    return re.sub(r"\s+", " ", (s or "").strip())


def _strip_wrapping_parens(s: str) -> str:
    m = re.fullmatch(r"\((.*)\)", s.strip())
    return m.group(1).strip() if m else s


def _baseline_name(raw: str) -> str:
    name = _strip_wrapping_parens(_clean(raw))
    return name if name.lower().endswith("baseline") else f"{name} Baseline"


@dataclass
class Component:
    key: str
    name: str
    component_type: str = COMPONENT_TYPE_HW
    component_revision: str | None = None
    manufacturer: str | None = None


@dataclass
class Release:
    version: str
    link: str | None = None


@dataclass
class Item:
    key: tuple
    name: str
    software_type: str
    level: str
    parent_key: tuple | None
    component_key: str | None
    releases: list[Release] = field(default_factory=list)


@dataclass
class Model:
    items: list[Item]                      # parent-first order
    components: dict[str, Component]
    index: dict[tuple, Item]

    def item_for(self, key: tuple) -> Item | None:
        return self.index.get(key)


def _enrich_software_files(current_items: list[dict]) -> list[dict]:
    """Return rows with each Software row tagged with its delivered file
    (``_file``), taken from the immediately following Software-component row(s).
    Software-component rows are consumed (not returned)."""
    out: list[dict] = []
    last_sw: dict | None = None
    for it in current_items:
        lvl = it.get("level", "")
        if lvl == LEVEL_SW:
            row = dict(it)
            row["_file"] = None
            last_sw = row
            out.append(row)
        elif lvl == LEVEL_SWC:
            if last_sw is not None and not last_sw.get("_file"):
                last_sw["_file"] = _clean(it.get("name", "")) or None
        else:
            last_sw = None
            out.append(dict(it))
    return out


def build_model(current_items: list[dict]) -> Model:
    """Build the v2 in-memory model from normalized current-state items."""
    rows = _enrich_software_files(current_items)

    # system-component names per subsystem (for instance collapsing)
    sys_names: dict[str, set[str]] = defaultdict(set)
    for it in rows:
        if it.get("level") == LEVEL_SYS:
            sys_names[_clean(it.get("subsystem"))].add(_clean(it.get("name")))

    def collapse(sub: str, sc: str) -> str:
        sc = _clean(sc)
        base = re.sub(r"\s+\d+$", "", sc)
        if base != sc and base in sys_names.get(_clean(sub), set()):
            return base
        return sc

    components: dict[str, Component] = {}
    sys_to_comp: dict[tuple, str] = {}
    for it in rows:
        if it.get("level") != LEVEL_HW:
            continue
        sub = _clean(it.get("subsystem"))
        csc = collapse(sub, it.get("system_component"))
        name = _clean(it.get("name"))
        if not name:
            continue
        if name not in components:
            components[name] = Component(
                key=name, name=name,
                component_revision=_clean(it.get("version")) or None,
                manufacturer=_clean(it.get("manufacturer")) or None,
            )
        sys_to_comp.setdefault((sub, csc), name)

    items: list[Item] = []
    index: dict[tuple, Item] = {}

    def add(item: Item) -> None:
        items.append(item)
        index[item.key] = item

    # --- Train baseline (root) ---
    train_key = ("train",)
    train_rows = [it for it in rows if it.get("level") == LEVEL_TRAIN]
    if train_rows:
        t = train_rows[0]
        add(Item(key=train_key, name=_baseline_name(t.get("name")),
                 software_type="Train Baseline", level=LEVEL_TRAIN,
                 parent_key=None, component_key=None,
                 releases=[Release(version=_clean(t.get("version")))]))

    # --- Subsystem baselines ---
    seen_sub: set[str] = set()
    for it in rows:
        if it.get("level") != LEVEL_SUB:
            continue
        sub = _clean(it.get("subsystem")) or _clean(it.get("name"))
        if sub in seen_sub:
            continue
        seen_sub.add(sub)
        add(Item(key=("sub", sub), name=_baseline_name(sub),
                 software_type="Subsystem Baseline", level=LEVEL_SUB,
                 parent_key=train_key if train_rows else None, component_key=None,
                 releases=[Release(version=_clean(it.get("version")))]))

    # --- Systems (collapsed system components) ---
    seen_sys: set[tuple] = set()
    for it in rows:
        if it.get("level") != LEVEL_SYS:
            continue
        sub = _clean(it.get("subsystem"))
        csc = collapse(sub, it.get("name"))
        skey = ("sys", sub, csc)
        if skey in seen_sys:
            continue
        seen_sys.add(skey)
        parent = ("sub", sub) if ("sub", sub) in index else (train_key if train_rows else None)
        add(Item(key=skey, name=csc, software_type="System", level=LEVEL_SYS,
                 parent_key=parent, component_key=sys_to_comp.get((sub, csc)),
                 releases=[Release(version=_clean(it.get("version")))]))

    # --- Software ---
    seen_sw: set[tuple] = set()
    for it in rows:
        if it.get("level") != LEVEL_SW:
            continue
        sub = _clean(it.get("subsystem"))
        csc = collapse(sub, it.get("system_component"))
        name = _clean(it.get("name"))
        version = _clean(it.get("version"))
        if not version or version == "—":
            continue  # skip malformed version-less rows
        wkey = ("sw", sub, csc, name)
        if wkey in seen_sw:
            continue  # one current version per logical software item
        seen_sw.add(wkey)
        skey = ("sys", sub, csc)
        parent = skey if skey in index else (("sub", sub) if ("sub", sub) in index else train_key)
        link = (RELEASE_ASSET_BASE + it["_file"]) if it.get("_file") else None
        sw_type = _clean(it.get("software_type")) or "Other"
        # structural types belong to the tree levels, never to a software leaf
        # (some source rows named "Baseline …" get mis-typed by the parser)
        if sw_type in ("Train Baseline", "Subsystem Baseline"):
            sw_type = "Other"
        add(Item(key=wkey, name=name, software_type=sw_type,
                 level=LEVEL_SW, parent_key=parent,
                 component_key=sys_to_comp.get((sub, csc)),
                 releases=[Release(version=version, link=link)]))

    return Model(items=items, components=components, index=index)


def apply_updates(model: Model, changes: list[dict]) -> int:
    """Append delivery-introduced versions as additional releases on the matching
    items (mirrors the demo's 'needs update'). Returns the count applied.
    Off by default for a pure v2 match; opt in via the CLI ``--apply-updates``."""
    applied = 0
    for ch in changes:
        level = ch.get("level", "")
        sub = _clean(ch.get("subsystem"))
        if level == LEVEL_SW:
            csc = re.sub(r"\s+\d+$", "", _clean(ch.get("system_component")))
            # try both collapsed and raw system component
            candidates = [("sw", sub, csc, _clean(ch.get("name"))),
                          ("sw", sub, _clean(ch.get("system_component")), _clean(ch.get("name")))]
        elif level == LEVEL_SUB:
            candidates = [("sub", sub)]
        else:
            continue
        item = next((model.index[k] for k in candidates if k in model.index), None)
        if item is None:
            continue
        current = {r.version for r in item.releases}
        introduced = ch.get("introduced") or ([ch.get("version", "")] if ch.get("version") else [])
        for v in introduced:
            v = _clean(v)
            if v and v not in current:
                item.releases.append(Release(version=v))
                current.add(v)
                applied += 1
    return applied


# --------------------------------------------------------------------------- #
# Emitters
# --------------------------------------------------------------------------- #
def to_fixture(model: Model) -> list[dict]:
    """Emit a Django ``loaddata`` fixture (list of {model, pk, fields}) directly
    comparable to ``example/v2.json``. This is the faithful match — it sets
    ``component_revision`` and the release ``parent`` chain, neither fully
    settable through the current REST API."""
    out: list[dict] = []

    man_pk: dict[str, int] = {}
    for c in model.components.values():
        if c.manufacturer and c.manufacturer not in man_pk:
            man_pk[c.manufacturer] = len(man_pk) + 1
            out.append({"model": "software.manufacturer", "pk": man_pk[c.manufacturer],
                        "fields": {"name": c.manufacturer}})

    comp_pk: dict[str, int] = {}
    for c in model.components.values():
        comp_pk[c.key] = len(comp_pk) + 1
        out.append({"model": "software.component", "pk": comp_pk[c.key],
                    "fields": {"name": c.name, "component_type": c.component_type,
                               "component_manufacturer": man_pk.get(c.manufacturer) if c.manufacturer else None,
                               "component_revision": c.component_revision}})

    item_pk: dict[tuple, int] = {it.key: i + 1 for i, it in enumerate(model.items)}
    for it in model.items:
        out.append({"model": "software.softwareitem", "pk": item_pk[it.key],
                    "fields": {"name": it.name, "software_type": it.software_type,
                               "parent": item_pk.get(it.parent_key) if it.parent_key else None,
                               "manufacturer": None,
                               "component": comp_pk.get(it.component_key) if it.component_key else None,
                               "vehicle_type": None, "consist_type": None}})

    rel_pk = 0
    current_rel_pk: dict[tuple, int] = {}
    rel_entries: list[dict] = []
    for it in model.items:  # parent-first → parent's current release pk is known
        parent_rel = current_rel_pk.get(it.parent_key) if it.parent_key else None
        for i, r in enumerate(it.releases):
            if not r.version:
                continue
            rel_pk += 1
            if i == 0:
                current_rel_pk[it.key] = rel_pk
            rel_entries.append({"model": "software.softwarerelease", "pk": rel_pk,
                                "fields": {"version_string": r.version,
                                           "release_archive_link": r.link,
                                           "release_archive_hash": None, "sbom_reference": None,
                                           "item": item_pk[it.key],
                                           "parent": [parent_rel] if parent_rel else []}})
    out.extend(rel_entries)
    return out


def push_via_api(model: Model, api_url: str = "http://localhost:8000/api/v1/",
                 dry_run: bool = False) -> dict:
    """Best-effort live push of the v2 model through the REST API.

    NOTE: the ``ComponentIn`` schema on ``main`` has no ``component_revision``
    field, so hardware revisions cannot be set this way (they are preserved in
    the loaddata fixture). Everything else — the 4-level tree, components,
    release links and the release parent chain — is created faithfully.
    """
    from rsscm_import.api_client import RsscmApiClient

    client = RsscmApiClient(api_url, dry_run=dry_run)
    comp_id: dict[str, int] = {}
    for c in model.components.values():
        mid = client.ensure_manufacturer(c.manufacturer) if c.manufacturer else None
        comp_id[c.key] = client.ensure_component(c.name, component_type=c.component_type, manufacturer_id=mid)

    item_id: dict[tuple, int] = {}
    current_rel_id: dict[tuple, int] = {}
    releases = 0
    for it in model.items:  # parent-first
        pid = item_id.get(it.parent_key) if it.parent_key else None
        cid = comp_id.get(it.component_key) if it.component_key else None
        obj = client.create_software_item(name=it.name, software_type=it.software_type,
                                          parent_id=pid, component_id=cid)
        item_id[it.key] = obj["id"]
        parent_rel = current_rel_id.get(it.parent_key) if it.parent_key else None
        for i, r in enumerate(it.releases):
            if not r.version:
                continue
            rel = client.create_software_release(
                item_id=obj["id"], version_string=r.version,
                release_archive_link=r.link or "",
                parent_ids=[parent_rel] if parent_rel else None)
            releases += 1
            if i == 0:
                current_rel_id[it.key] = rel["id"]
    client.close()
    return {"components": len(model.components), "items": len(model.items), "releases": releases}
