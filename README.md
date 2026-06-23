# RSSCM Baseline Builder

> The "magic" import pipeline that turns a chaotic supplier software delivery
> into a clean, standardized train-software baseline — and pushes it to the
> RSSCM backend so everyone works from the same source of truth.

Part of the [Hack4Rail 2026](https://hack4rail.org/) challenge
*Rolling Stock Software Configuration Management*, built by the **tools** group.
The data-model / backend lives in the companion repo
[`OpenRail-Playground/RSSCM`](https://github.com/OpenRail-Playground/RSSCM).

---

## The problem (in plain words)

When a supplier delivers new software for a train, they ship a **chaotic bundle**:
Excel sheets, Word documents, PDFs, firmware blobs, ZIPs — every supplier and
every delivery looks different. Someone then has to figure out, by hand:

- *What* is actually in this delivery?
- *Which versions* are new compared to what is already on the train?
- *What therefore needs to be installed* — and nothing more?

Doing this manually is slow and error-prone. In our test delivery a human
reviewer counted the changes by hand, **missed one**, and was **misled by
inconsistent rows** in a secondary table.

## What this tool does

The Baseline Builder automates that work in four steps:

1. **Read the delivery** — open the supplier bundle, safely unpack it, and parse
   every file (Excel / Word / PDF …) into one common structure.
2. **Read the current train state** — what software is on the train today.
3. **Diff** — compare the two and work out exactly which software is **new** or
   **updated**, ignoring duplicates and noise.
4. **Publish** — push that clean baseline to the RSSCM backend (and store any
   binaries), so the change is recorded against the standard data model.

The result is a **clean baseline**: a short, trustworthy list of "install
these, and only these" — instead of a 500-row spreadsheet.

## Architecture

```
                         Train Assets (current train state)
                         source: CSV export, REST API, or a
                         previous "Ladeliste"
                                     │
                                     ▼
Vendor ──► Software "Ladeliste" ──►  ┌─────────────────────────┐
           (chaotic ZIP:            │  Baseline Builder        │
            xls, pdf, docx,         │  (this repo, "magic")    │
            csv, exe, bin)          └───────────┬─────────────-┘
                                       │                    │
                      REST API: create │                    │ binaries, SBOMs
                      / update metadata │                    ▼
                                       ▼            ┌──────────────────┐
                              ┌──────────────┐      │  Asset Storage   │
   Software Responsible ────► │ Django Webapp │◄────┘   (href links)
   Person (reviews)          │  (RSSCM API) │
                              └──────┬───────┘
                                     │ export a single Baseline (standard)
                                     ▼
                                   Train  ◄── Workshop Personnel (install)
```

The Django backend is a **proof-of-concept of the data model and can be
replaced**; the Baseline Builder talks to it only through the REST API.

## The standard data model

Every parser, no matter the input format, normalizes into the same RSSCM model
(mirrors the Django models):

| Entity | Meaning |
|---|---|
| `Manufacturer` | Who makes the component / software |
| `Component` | The thing that *hosts* software (a system component / device) |
| `SoftwareItem` | A node in the software tree (name + type), can have a parent |
| `SoftwareRelease` | A concrete version of a `SoftwareItem` (version, checksum, link, SBOM) |
| `VehicleType` / `ConsistType` | Which train / formation the software applies to |

The hierarchy the parsers reconstruct:

```
Train baseline → Subsystem → System component → { Hardware | Software → Software component }
```

## Quickstart

```bash
# 1. Install (uses uv)
uv sync

# 2. See the commands
uv run rsscm-import --help

# 3. Run the full pipeline (dry-run prints what *would* be posted)
uv run rsscm-import run \
  --delivery        ./Chaos_HackTrain_Ladeliste.zip \
  --current-state   ./Train_Asset_Baseline_Hacktrain.xlsx \
  --dry-run
```

Drop `--dry-run` to actually post to the backend (default
`http://localhost:8000/api/v1/`).

### Commands

| Command | What it does |
|---|---|
| `ingest <delivery>` | Safely unpack & classify every file (zip-bomb guarded), show SHA-256 |
| `parse <delivery>` | Parse any delivery into normalized items (JSON) |
| `current-state <file>` | Load the current train state from a source |
| `diff --delivery … --current …` | Show NEW / UPDATED / UNCHANGED (deduplicated) |
| `push --delivery … --current …` | Post the clean baseline to the backend |
| `run …` | The whole pipeline end-to-end |

## What gets created in the backend

Running the pipeline on our test delivery produces this **clean baseline of 5
changes** (3 software-level + 2 subsystem-level):

| Subsystem | Software | Change |
|---|---|---|
| Air Conditioning (HVAC) | 332 Operating System Software | `V4.1 A → V4.8 A` |
| Train Control | Operating System | `V1.5E → V1.6E` |
| Video Surveillance (CCTV) | Kernel Software | `G1.5/G2.7 → G1.6/G2.8` |
| Remote Data Transmission (RDA) | *(subsystem)* | `12.0 → 12.5` |
| Toilet (WC) | *(subsystem)* | `9.0 → 9.2` |

Pushing the software-level changes creates these records via the REST API
(real output):

```jsonc
// POST /api/v1/components/
{ "id": 1, "name": "HVAC Front Box",      "component_type": "Subsystem/Grouping Category" }
{ "id": 2, "name": "MRB4 [ – Cab 2 ]",    "component_type": "Subsystem/Grouping Category" }
{ "id": 3, "name": "Video 1C1D",          "component_type": "Subsystem/Grouping Category" }

// POST /api/v1/software-items/
{ "id": 1, "name": "332 Operating System Software", "software_type": "Operating System", "component_id": 1 }
{ "id": 2, "name": "Operating System",              "software_type": "Operating System", "component_id": 2 }
{ "id": 3, "name": "Kernel Software",               "software_type": "Firmware",          "component_id": 3 }

// POST /api/v1/software-releases/
{ "id": 1, "version_string": "V4.8 A",          "item_id": 1, "release_archive_hash": null, "sbom_reference": null }
{ "id": 2, "version_string": "V1.6E",           "item_id": 2, "release_archive_hash": null, "sbom_reference": null }
{ "id": 3, "version_string": "1. G1.6 / 2.G2.8","item_id": 3, "release_archive_hash": null, "sbom_reference": null }
```

> `release_archive_hash`, `release_archive_link` and `sbom_reference` are filled
> in when the delivery actually contains the binaries + SBOM (e.g. the
> `HVAC_Firmware_*.zip` example). This Ladeliste is *metadata-first*, so those
> fields are `null` and the binaries (when present) go to **Asset Storage**.

## Who sees what

**Software Responsible Person** (works in the Django webapp)
After the Baseline Builder posts, they see exactly the **changes that need
review** — not 500 unchanged rows. For our delivery:

- `332 Operating System Software` → **V4.8 A** on *HVAC Front Box*
- `Operating System` → **V1.6E** on *MRB4 (Cab 2)*
- `Kernel Software` → **G1.6 / G2.8** on *Video 1C1D*

…each with its version, the component it belongs to, and (when present) the
checksum / SBOM / download link for provenance. They review and approve the
baseline.

**Workshop Personnel** (at the train)
They receive an **exported single baseline (standard format)** for a specific
train/consist — the actionable "to-do" list:

> Install **V4.8 A** of *332 Operating System Software* on the **HVAC Front Box**;
> install **V1.6E** of the *Operating System* on **MRB4**; install
> **G1.6/G2.8** of the *Kernel Software* on **Video 1C1D**.
> (plus checksum to verify each file before flashing)

Everything that is already up to date is omitted, so they flash only what
changed — *"all updates have to be done, otherwise the train is not allowed to
leave."*

## Why a pluggable parser design

Supplier formats vary from delivery to delivery, so parsing is **pluggable**:

- `parsers/base.py` — the standard model + a registry that dispatches each file
  to a parser by type (with a per-component override hook).
- `parsers/xlsx_parser.py`, `docx_parser.py`, `pdf_parser.py` — one per format,
  all feeding a shared, header-driven tree normalizer.

Supporting a new format = add one parser and register it. Nothing else changes.

## Robustness highlights

- **Zip-bomb guard** on ingest (depth / size / count limits).
- **Set-based diff**: handles the same node appearing many times with mixed
  versions; reports one change, not dozens of duplicate rows.
- **Whitespace-insensitive matching**: tolerant of PDF/extraction artifacts that
  inject spurious spaces into filenames.
- **Scoped-tree authority**: uses each file's authoritative per-subsystem tree
  and ignores inconsistent "context" tables — which is how the tool caught a
  change a manual review missed and avoided two false positives.

## Testing

```bash
uv run pytest            # 26 tests
```

Includes per-parser tests, set-based diff tests, an integration test that locks
in the reconciled expected changes, and **live API round-trip tests** that
auto-skip when the backend isn't running.

To run against the live backend (in the companion `RSSCM` repo):

```bash
uv run rsscm/manage.py migrate
uv run rsscm/manage.py runserver
```

## Limitations / future work

- Current-state-from-REST-API reader is stubbed (file/zip export works today).
- Binaries are not yet matched to their metadata item to auto-fill the release
  checksum/link; asset storage hashes them separately.
- Subsystem/parent linking in the backend tree is flat for now (component-level).
- Intra-document data conflicts (Tree vs context tables) are resolved in favor
  of the Tree; flagging them as data-quality warnings would be a useful add.
