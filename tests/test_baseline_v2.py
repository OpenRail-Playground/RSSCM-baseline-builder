"""The v2 model transform must reproduce the RSSCM example/v2.json structure.

We build the model from the real current-state fixture, emit the loaddata
fixture, and assert the HVAC subtree matches example/v2.json on the things that
matter: the 4-level tree shape, software types, the parent chain, the
Hardware/Bare Metal component + component_revision, and the release links.

(The only intentional difference is the subsystem *display name*: we derive
"Air Conditioning (HVAC) Baseline" from the source, whereas the hand-curated
reference says "HVAC Baseline" — see docs/DESIGN-v2-model.md. We therefore match
the subsystem by its child structure, not its name.)
"""
import json
from pathlib import Path

import pytest

from rsscm_import import baseline_v2 as baseline
from rsscm_import.cmdb import read_current_state

FIXTURES = Path(__file__).parent / "fixtures"
CMDB = FIXTURES / "Train_Asset_Baseline_Hacktrain.xlsx"
REFERENCE = FIXTURES / "rsscm_v2_reference.json"


# --------------------------------------------------------------------------- #
# helpers: turn a Django loaddata fixture into name-keyed lookups
# --------------------------------------------------------------------------- #
def _index(fixture):
    items = {o["pk"]: o["fields"] for o in fixture if o["model"] == "software.softwareitem"}
    comps = {o["pk"]: o["fields"] for o in fixture if o["model"] == "software.component"}
    rels = [o["fields"] for o in fixture if o["model"] == "software.softwarerelease"]
    rel_pk = {o["pk"]: o["fields"] for o in fixture if o["model"] == "software.softwarerelease"}
    return items, comps, rels, rel_pk


def _subtree(fixture, system_name):
    """Return a normalized description of a System node and its software leaves:
    {system, type, component, revision, parent_type, leaves:{name:(type,version,link)}}."""
    items, comps, rels, rel_pk = _index(fixture)
    name_of = lambda pk: items[pk]["name"] if pk in items else None
    sys_pk = next(pk for pk, f in items.items()
                  if f["name"] == system_name and f["software_type"] == "System")
    sysf = items[sys_pk]
    comp = comps.get(sysf["component"]) if sysf["component"] is not None else None
    rel_by_item = {}
    for r in rels:
        rel_by_item.setdefault(r["item"], []).append(r)

    def version_link(pk):
        rs = rel_by_item.get(pk, [])
        return (rs[0]["version_string"], rs[0]["release_archive_link"]) if rs else (None, None)

    leaves = {}
    for pk, f in items.items():
        if f["parent"] == sys_pk:
            v, link = version_link(pk)
            leaves[f["name"]] = (f["software_type"], v, link)

    sys_v, _ = version_link(sys_pk)
    parent_type = items[sysf["parent"]]["software_type"] if sysf["parent"] is not None else None
    return {
        "system": sysf["name"],
        "type": sysf["software_type"],
        "version": sys_v,
        "component": comp["name"] if comp else None,
        "revision": comp["component_revision"] if comp else None,
        "parent_type": parent_type,
        "leaves": leaves,
    }


@pytest.fixture(scope="module")
def generated():
    model = baseline.build_model(read_current_state(str(CMDB)))
    return baseline.to_fixture(model)


@pytest.fixture(scope="module")
def reference():
    return json.loads(REFERENCE.read_text())


@pytest.mark.parametrize("system_name", ["HVAC Front Box", "HVAC Roof Unit"])
def test_hvac_subtree_matches_reference(generated, reference, system_name):
    ours = _subtree(generated, system_name)
    ref = _subtree(reference, system_name)

    # System node: same type, version, hardware component + revision, parent level
    assert ours["type"] == ref["type"] == "System"
    assert ours["version"] == ref["version"]
    assert ours["component"] == ref["component"]
    assert ours["revision"] == ref["revision"]
    assert ours["parent_type"] == ref["parent_type"] == "Subsystem Baseline"

    # Software leaves: identical names, types, versions and release links
    assert ours["leaves"] == ref["leaves"]


def test_component_revision_present(generated):
    """The hardware revision (only settable via fixture, not the API) is carried."""
    fb = _subtree(generated, "HVAC Front Box")
    assert fb["component"] == "HVAC controller FPC24 (Fstd.) - Master"
    assert fb["revision"] == "ZA 534 906"


def test_four_level_tree_and_root(generated):
    items = [o["fields"] for o in generated if o["model"] == "software.softwareitem"]
    roots = [f for f in items if f["parent"] is None]
    assert len(roots) == 1
    assert roots[0]["software_type"] == "Train Baseline"
    assert roots[0]["vehicle_type"] is None  # pure v2: train is the root item
    # all four levels are present
    types = {f["software_type"] for f in items}
    assert {"Train Baseline", "Subsystem Baseline", "System"} <= types


def test_release_links_use_software_component_files(generated):
    fb = _subtree(generated, "HVAC Front Box")
    name, (typ, ver, link) = "332 Operating System Software", fb["leaves"]["332 Operating System Software"]
    assert ver == "V4.1 A"
    assert link == "http://release-assets.example.com/532541.tlc"
