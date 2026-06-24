# Demo runbook (pitch)

A 3-minute, end-to-end walkthrough: **chaotic delivery in → standardized,
queryable train baseline out**, visualized in the Django admin.

## Setup (once)

```bash
chmod +x scripts/*.sh

# Terminal 1 — start the backend + admin user (http://127.0.0.1:8000)
./scripts/demo_backend.sh
```

Admin login: **`admin`** / **`hack4rail2026`** → http://127.0.0.1:8000/admin/

> Prerequisite: **graphviz** (`brew install graphviz`) — the backend's `/graph/`
> view imports `pygraphviz` at startup. `demo_backend.sh` builds `pygraphviz`
> into a local `.demo-venv` against the brew graphviz and runs migrations. The
> SQLite DB lives in the RSSCM repo and is shared regardless of venv.

## The pitch (Terminal 2, in this repo)

**1. Show the inputs** — the messy reality:
```bash
unzip -l ../Chaos_HackTrain_Ladeliste.zip   # xls, docx, pdf … one per subsystem
```

**2. (optional) Start clean** so the audience sees objects appear live:
```bash
./scripts/demo_reset.sh                      # empty DB + admin
```
Refresh the admin → the tables are empty.

**3. Run the client** — the "magic" import:
```bash
uv run rsscm-import populate \
  --current-state ../Train_Asset_Baseline_Hacktrain.xlsx \
  --delivery      ../Chaos_HackTrain_Ladeliste.zip \
  --vehicle-type  Hacktrain
```
→ `Seeded 91 baseline items; applied 5 update release(s).`

**4. Visualize in the admin** (refresh the browser):
- http://127.0.0.1:8000/admin/software/softwareitem/ — 91 software items
- http://127.0.0.1:8000/admin/software/softwarerelease/ — 96 releases
- http://127.0.0.1:8000/admin/software/component/ — 48 components
- http://127.0.0.1:8000/graph/ — backend's built-in graph visualization

**5. Query back — the business questions:**

*"What does Train Hacktrain need updated?"*
```bash
uv run rsscm-import query --vehicle-type Hacktrain
```
→ exactly the 5 real changes, e.g.
`⚠ 332 Operating System Software: installed V4.1 A → available V4.8 A`

*"What software runs on the HVAC Front Box subcomponent?"*
```bash
uv run rsscm-import query --component "HVAC Front Box"
```

**6. Same data, straight from the REST API** (what any tool would consume):
```bash
curl -s "http://localhost:8000/api/v1/software-items/?vehicle_type_id=1" | python3 -m json.tool | head
curl -s "http://localhost:8000/api/v1/software-releases/" | python3 -m json.tool | head
```

## The one-liner story

A supplier ships a **chaotic bundle** (Excel + Word + PDF + firmware). One
command turns it into a **standardized baseline in the database**, tells the
**Software Responsible Person** exactly which 5 things changed (out of ~90), and
lets **Workshop Personnel** pull the install list per train or per component —
all through one open REST API.
