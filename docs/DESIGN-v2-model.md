# Design: matching the RSSCM data model (`example/v2.json`)

The baseline builder transforms the normalized current-state tree into the
RSSCM backend's data model, exactly as exemplified by `example/v2.json` on the
backend's `main`. This note records the design decisions behind
`rsscm_import/baseline_v2.py`.

## Target shape

A four-level `SoftwareItem` tree, with hardware modelled as `Component`s:

```
Hacktrain Baseline            SoftwareItem(type="Train Baseline")        ← root
└─ HVAC Baseline              SoftwareItem(type="Subsystem Baseline")
   └─ HVAC Front Box          SoftwareItem(type="System")  ─ component ─▶ Component
      ├─ 332 OS Software       SoftwareItem(type="Operating System")        (Hardware/
      ├─ Application           SoftwareItem(type="Application")              Bare Metal,
      └─ TMS OS Software       SoftwareItem(type="Operating System")        revision)
```

Each `SoftwareRelease` has a `parent` (M2M) pointing at the parent item's
current release, so the release graph mirrors the item tree.

## Source → model mapping

Verified field-by-field against `example/v2.json`:

| Source level (NormalizedItem) | Model |
|---|---|
| `Train baseline` | `SoftwareItem(type="Train Baseline")` — the root |
| `Subsystem` | `SoftwareItem(type="Subsystem Baseline")` |
| `System component` | `SoftwareItem(type="System")`, `component` = its hardware |
| `Hardware` | `Component(type="Hardware/Bare Metal", component_revision=<row version>)` |
| `Software` | `SoftwareItem(type=<software_type>)`, `component` = same hardware |
| `Software component` | the delivered file → release `release_archive_link` |

Example: HVAC `Hardware` row version `ZA 534 906` becomes the component
`component_revision`; the `Software component` file `532541.tlc` becomes
`http://release-assets.example.com/532541.tlc`.

## Decisions

### 1. Train is the root `SoftwareItem` (pure match)
The train is represented by the root `Train Baseline` item, and items have
`vehicle_type = None` — matching `example/v2.json` exactly. We do **not** use a
`VehicleType` (that was the earlier demo/prototype approach; not carried over).

### 2. Output method — fixture is faithful, API push is best-effort
Two emitters:

- **`to_fixture` (default for `--fixture`)** — a Django `loaddata` fixture,
  directly comparable to `example/v2.json`. **This is the faithful match**: it is
  the only way to set `component_revision` and the release `parent` chain.
- **`push_via_api`** — pushes the same tree live through the REST API. The
  `ComponentIn` schema on the backend `main` has **no `component_revision`
  field**, so revisions cannot be set this way (everything else — the tree,
  components, release links, release parent chain — is created faithfully). If
  revisions are wanted live, the backend's `ComponentIn`/`create_component`
  would need a one-line addition; until then, use the fixture.

Usage:

```bash
# faithful fixture (recommended for matching v2.json)
rsscm-import populate --current-state Train_Asset_Baseline_Hacktrain.xlsx \
    --fixture hacktrain_baseline.json
python manage.py loaddata hacktrain_baseline.json     # in the RSSCM backend

# or push live (component_revision will be null)
rsscm-import populate --current-state Train_Asset_Baseline_Hacktrain.xlsx
```

### 3. Naming, instance collapsing, dedup (cosmetic / data-hygiene)
- **Naming** is derived from the source: the train and subsystem levels gain a
  trailing " Baseline"; the train also has wrapping parentheses stripped
  (`(Hacktrain)` → `Hacktrain Baseline`). System/software keep their source
  name with internal whitespace collapsed. *Known difference:* the hand-curated
  reference uses short names like `HVAC Baseline`, whereas we derive
  `Air Conditioning (HVAC) Baseline` from the source. We cannot infer the
  curated short form, so tests match the subsystem by its child structure, not
  its display name.
- **Instance collapsing**: a system component named `<base> <digits>`
  (e.g. `HVAC Roof Unit 7024`) collapses onto its base (`HVAC Roof Unit`) when
  that base also exists in the same subsystem — yielding v2's clean set.
- **Software dedup**: one current release per `(subsystem, system, name)` (the
  first/canonical instance), representing a single train baseline.
- **Mislabeled structural types**: some source rows named `Baseline …` are typed
  by the parser as `Subsystem Baseline`; on a software leaf this is coerced to
  `Other`, so structural baseline types only ever appear on the tree levels.

### Single model path
Per project direction we iterate the prototype into **one** model rather than
keeping the old flat/`VehicleType` path. `populate` has a single behaviour (no
`--model` switch); `--apply-updates` optionally folds a delivery's introduced
versions in as extra releases (off by default for a pure current-baseline
match).

## Verification

`tests/test_baseline_v2.py` builds the model from the real current-state fixture
and asserts the generated HVAC subtree matches `tests/fixtures/rsscm_v2_reference.json`
(types, parent chain, `component_revision`, release links, four-level tree,
train-as-root). Full suite: 35 passing.

Live load: `loaddata` of the full fixture installs 292 objects — 130 items
(1 Train Baseline, 12 Subsystem Baseline, 46 System, plus OS/Application/Firmware
leaves), 32 components (all with `component_revision`), 130 releases (129
parented, 52 with links); `/graph` renders the four-level tree.
