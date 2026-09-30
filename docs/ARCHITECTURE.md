# Architecture

```
┌──────────────────────── frontend (Next.js 14, React, MapLibre) ─────────────────────────┐
│ /gov (dashboard, map, anomalies, population, institutions, vehicles, alerts, copilot,   │
│ reports, settings)  /institution  /citizen  /traveller  /rescue   ← role-based sign-in   │
└───────────────────────────────▲──────────────────────────────────────────────────────────┘
                                │ JSON / GeoJSON over /api/v1 (bearer token)
┌───────────────────────────────┴────────── backend (FastAPI) ─────────────────────────────┐
│ api/routes.py  auth.py (roles)  copilot.py (Gemini tools)  reports.py (PDF/CSV)           │
│ service.py  ── orchestrates the pipeline and keeps the latest run in memory              │
│   data/synthetic.py │ data/loaders.py   ingest (synthetic or ERA5/NEPS/IMD/OSM)          │
│   pipeline/preprocess.py                QC, gap fill, standardised anomalies             │
│   pipeline/detection.py + models.py     objects, ML type/severity, anomaly score         │
│   pipeline/tracking.py                  association, motion, ML path extension           │
│   pipeline/impact.py + data/population  rings, Census exposure, assets, vehicles         │
│   alerts/composer.py, gemini.py         drafts (validated numbers), summaries            │
│   alerts/dispatch.py                    SMS / email / push / app + delivery log          │
│ storage.py (SQLite; schema mirrors db/schema_postgis.sql)                                │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

## Pipeline details

**Preprocessing.** Values outside physical ranges become missing; missing cells are filled with a NaN-aware 3×3 mean. Each variable is standardised against the monthly climatology, z = (x − μ)/σ; precipitation uses cube-root space because it is strongly skewed.

**Detection.** An "extremeness" field max(z_precip, z_t2m, −z_t2m, z_wind, −z_mslp) on the ensemble mean is thresholded at 2.5σ and labelled into connected objects (≥ 3 cells). Each object gets 16 features (peak/mean anomalies of the 4 variables, log area, ensemble exceedance probability, member-centroid spread, location, season, lead time). A gradient-boosted classifier predicts the type (heavy rainfall, cyclone, heatwave, cold wave or noise) and a second one the severity; an Isolation Forest trained on noise objects gives an anomaly score.

**Evaluation** uses an **event-based hold-out**: whole simulated scenarios are held out so near-identical objects never sit on both sides of the split. Metrics shown in Reports: type accuracy vs a physically-motivated rule baseline, macro F1, detection precision/recall, false-alarm rate, severity accuracy.

**Tracking.** Objects are associated between consecutive steps with the Hungarian algorithm; the cost is distance to the position predicted from the track's current velocity, gated at 25 km/h × gap + 60 km, with type-compatibility rules. Motion is a least-squares fit over the last 4 positions. Beyond the last detection a gradient-boosting displacement model (trained on synthetic curving tracks) extends the path for 48 h with a widening uncertainty cone.

**Impact zones.** Base radii 3/5/8 km, scaled by severity (×0.85–1.4), stretched and shifted forward along motion (up to +50%), outer ring widened by ensemble spread. Each event's *headline* time step is the one with the most people exposed among steps within one severity level of the strongest.

**Exposure.** Rings are sampled on a 250 m grid; each sample takes the density of its Census unit (BBMP ward, else district), then totals are rescaled to the exact ring area and projected to today. Vehicles are flagged when inside a ring, or heading within 30° of the zone centre and projected (at current speed) to enter a ring within 60 minutes; a detour around the outer ring is suggested.

**Alerts.** Officials and drivers (standing order) are notified automatically; citizens, schools, hospitals and rescue orders wait for approval. Every number in a Gemini-written draft must match the structured facts, otherwise the template is used. Deliveries are logged per channel; without credentials they are marked `simulated`.

**Copilot.** Gemini receives a system prompt forbidding invented facts and 11 function declarations (events, population in zone, assets, vehicles, district/ward population, geocoding, risk at a location, routing via OSRM, alert drafting). The loop runs up to 6 tool rounds; every call is returned to the UI and written to the audit log. Without a key, a deterministic intent router calls the same tools.

## Security & privacy
* Secrets only in `backend/.env` (git-ignored). The browser never sees Gemini/Twilio/SMTP keys.
* Role-based access on every route (`official`, `institution`, `rescue`, `citizen`, `traveller`).
* No Aadhaar or personal identifiers; population is aggregate Census data; demo people and vehicles are fictional.
* Replace the demo HMAC login with a government identity provider for real use.

## Moving to production
* Swap SQLite for PostgreSQL/PostGIS using `db/schema_postgis.sql`.
* Schedule `POST /api/v1/pipeline/run` after each NEPS cycle (00/12 UTC).
* Configure real channels (Twilio / SMTP / Firebase) and official recipient lists.
