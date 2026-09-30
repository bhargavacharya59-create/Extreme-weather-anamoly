# WeatherPulse AI — Detect. Track. Alert. Protect.

**Smart India Hackathon 2026 · Problem statement SIH26078** — *AI-driven spatio-temporal tracking of extreme weather anomalies in medium-range forecasts* · Team **404 THINKER'S**

WeatherPulse AI turns 3–10 day ensemble weather forecasts into local, actionable impact intelligence:

1. **Detect** unusual forecast patterns against the historical baseline (ML classifier + anomaly score).
2. **Track** each anomaly across forecast steps, with speed, direction, ensemble agreement and path uncertainty.
3. **Estimate impact** inside dynamic 3 / 5 / 8 km risk rings: **citizens in the zone from official Census of India 2011 data**, schools, hospitals, rescue units, and **vehicles moving toward the zone**.
4. **Alert** officials, institutions, citizens, rescue teams and drivers — drafts are written from verified facts (Gemini optional) and nothing reaches the public without an official's approval.

> **Prototype.** The forecast scenario, institutions and vehicles are **synthetic demo data** and are labelled as such everywhere in the UI. Population figures are **real Census 2011 data**, projected to today. WeatherPulse does not replace IMD warnings.

---

## What's inside

| Portal | Who | Highlights |
|---|---|---|
| **Government command dashboard** (`/gov`) | District officials | KPIs incl. **citizens in anomaly areas**, live risk map with rings, tracks and uncertainty cone, 10-day timeline player, anomaly details, ward-level population, institutions, **vehicles heading into zones**, alert approval workflow with delivery log, reports (PDF/CSV), analytics & model metrics, settings |
| **AI Copilot** (`/gov/copilot`) | Officials | Ask in plain language. Gemini (function calling) queries the **Census dataset, events, institutions, vehicles and the map** and answers only from those results; works offline with rule-based tool routing |
| **Institution portal** (`/institution`) | Schools, colleges, hospitals | Site risk, countdown, expected rain, preparedness checklist, acknowledge alert |
| **Citizen app** (`/citizen`) | Residents | Location-based alert, what to do, rain timeline, nearest shelter, helplines, English / ಕನ್ನಡ headings |
| **Traveller / driver app** (`/traveller`) | Bus & fleet drivers | "Risk zone ahead in N min", current vs **safer route**, spoken alert |
| **Rescue team app** (`/rescue`) | NDRF / SDRF / fire | Pre-position orders, staging point, status flow, report constraints |

### Logins
* **Every** school/college, hospital and rescue unit has its own account — **username = its name** (e.g. `Govt. High School, Singasandra, Bengaluru`), unique password. Bus drivers log in with their bus number; the government has one account (`GovtOfficer`).
* **Citizens register themselves** (mobile number + password + home area) and then sign in with their mobile number.
* All demo logins are in **[`data/demo_accounts.xlsx`](data/demo_accounts.xlsx)** (regenerate with `python -m scripts.export_accounts`). The sign-in page also shows a "Judge demo" login for each role.
* Passwords are stored only as salted PBKDF2 hashes. Demo data only — never reuse these passwords.

## Quick start (local)

Requirements: **Python 3.10+**, **Node.js 18.17+**, Git.

### 1. Backend (FastAPI) — terminal 1

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate      macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # Windows: copy .env.example .env   — then add GEMINI_API_KEY (optional)
uvicorn app.main:app --reload --port 8000
```

On the **first start** the backend trains the ML models (~1 minute) and runs the forecast pipeline; the sign-in page shows "warming up" until it is ready. API docs: http://localhost:8000/docs

### 2. Frontend (Next.js) — terminal 2

```bash
cd frontend
npm install
cp .env.local.example .env.local    # Windows: copy .env.local.example .env.local
npm run dev
```

Open **http://localhost:3000** and click a demo role.

### 3. (Recommended) exact district boundaries

Population outside Bengaluru uses district densities; for exact point-in-district lookups instead of nearest-centroid, run once:

```bash
cd backend
python -m scripts.prepare_reference_data
```

### Optional
* **Gemini key** → AI-written alerts, translations and a conversational Copilot. Get one at https://aistudio.google.com/apikey and put it in `backend/.env` (never in the frontend, never in Git).
  * Gemini is used **on demand only** (Copilot questions, "Draft alert", translations). The automatic drafts written on every pipeline run use verified templates, so startup doesn't burn your free quota. Set `WP_GEMINI_IN_PIPELINE=1` to let Gemini write those too.
  * **`Gemini HTTP 429` / "quota exceeded"** = the free-tier limit is used up. The app keeps working (templates + offline Copilot) and pauses Gemini automatically until the limit resets. Options: wait (per-minute limits reset in a minute, daily ones at midnight Pacific time), use `GEMINI_MODEL=gemini-2.5-flash-lite` (higher free limits), enable billing on the key, or set `WP_USE_GEMINI=0` to turn Gemini off.
* `python -m scripts.train_models` — retrain the models (also available from Settings → Retrain).
* `python -m scripts.generate_synthetic_data` — export the synthetic datasets to `data/synthetic/`.
* `python -m scripts.export_accounts` — write every demo login to `data/demo_accounts.xlsx`.
* **Map:** satellite (Esri World Imagery, no key) or streets (OpenFreeMap, no key) via the layers button. Optional `NEXT_PUBLIC_MAPTILER_KEY` in `frontend/.env.local` switches satellite to MapTiler Hybrid for production use.
* `python -m pytest -q` (in `backend/`) — run the test suite.
* `docker compose up --build` — run both services in containers.

## How it works

```
Forecast ensemble ──► preprocessing ──► anomaly detection ──► tracking ──► impact zones ──► exposure ──► alerts
(NEPS-like, 6 members,   QC, gap fill,     z-score objects +     Hungarian     3/5/8 km rings,   Census 2011       drafts → approval
 0.25°, 0–240 h)         standardise vs    ML type/severity/     matching,     adapted to        population,       → delivery log
                         ERA5-like normals anomaly score         ML path       severity, speed,  institutions,     (SMS/email/push/app)
                                                                 extension     uncertainty       vehicles
```

| Plan component | Implementation | Trained? |
|---|---|---|
| Model 1 · anomaly detection | Standardised anomalies vs climatology → connected objects → gradient-boosted classifier (type + severity) + Isolation Forest score (`app/pipeline/detection.py`, `models.py`) | **Yes** — event-based hold-out: 87% type accuracy vs 68% rule baseline; detection precision 0.90 / recall 0.88 / false-alarm 12% |
| Model 2 · tracking | Hungarian assignment with velocity-predicted gating; least-squares motion; ML displacement model for extension (`tracking.py`) | Path model trained on synthetic tracks |
| Model 3 · ensemble | Member exceedance probability and centroid spread → confidence and uncertainty cone | No (statistics) |
| Model 4 · impact | Adaptive rings; 250 m sampling of Census density; asset and vehicle intersection (`impact.py`, `data/population.py`) | No (GIS) |
| Model 5 · alerts | Role-specific templates + Gemini wording with **number validation** against the facts (`alerts/composer.py`) | No (API) |
| Copilot | Gemini function calling over 11 read-only tools, audit-logged (`copilot.py`) | No — grounded, not fine-tuned |

See **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**, **[docs/DATASETS.md](docs/DATASETS.md)** and **[docs/API.md](docs/API.md)**.

## Data

| Data | Status in this repo | Source |
|---|---|---|
| Population (Bengaluru, 198 wards) | **Official** — committed | Census of India 2011 via DataMeet `Municipal_Spatial_Data` (CC BY-SA 2.5 IN) |
| Population (640 districts) | **Official** — committed | Census of India 2011 district PCA |
| Forecast ensemble, climatology | Synthetic (same shape as NEPS / ERA5) | `app/data/synthetic.py`; real loaders in `app/data/loaders.py` |
| Schools, hospitals, rescue units | Synthetic fictional records | swap for OpenStreetMap export via `load_osm_assets()` |
| Vehicles, citizens, incident reports | Synthetic | `scripts/generate_synthetic_data.py` |

## Repository layout

```
backend/   FastAPI app (app/), scripts/, tests/, requirements*.txt, .env.example
frontend/  Next.js 14 app router (app/), components/, lib/
data/      reference/ (official Census data), synthetic/ (demo data); raw/, models/ are generated
docs/      architecture, datasets, API, UI mockups
```

## Team

404 THINKER'S · SIH 2026. Built with help from Claude (Anthropic).

## Screenshots

Rendered from the running app with a test map renderer (the real app draws the same layers on an OpenStreetMap base map).

| | |
|---|---|
| ![Sign in](docs/screenshots/01-login.png) | ![Government overview](docs/screenshots/02-gov-overview.png) |
| ![Anomaly details](docs/screenshots/03-anomaly-detail.png) | ![Population](docs/screenshots/04-population.png) |
| ![AI Copilot](docs/screenshots/05-copilot.png) | ![Institution portal](docs/screenshots/06-institution.png) |
| ![Citizen and driver apps](docs/screenshots/07-citizen-traveller.png) | ![Reports](docs/screenshots/09-reports.png) |
