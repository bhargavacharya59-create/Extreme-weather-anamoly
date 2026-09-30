# Datasets

WeatherPulse separates **historical baseline**, **forecast**, **exposure** and **operational** data. Every dataset has a synthetic stand-in with the same shape, so the pipeline runs end to end today and each source can be switched to real data independently.

## Already included (official)

| File | Content | Source & licence |
|---|---|---|
| `data/reference/bbmp_wards_census2011.geojson` | 198 Bengaluru BBMP wards (2012 delimitation): boundary, Census 2011 total / male / female / SC / ST population, area | DataMeet `Municipal_Spatial_Data/Bangalore/BBMP_oldWards.geojson`, CC BY-SA 2.5 India |
| `data/reference/census2011_districts.csv` | 640 districts: population, sex, literacy, households, age groups | Census of India 2011 district PCA (mirror: github.com/nishusharma1608/India-Census-2011-Analysis) |
| `data/reference/districts_density.csv` | District centroid, area, population and density (boundaries matched to Census names incl. renamed districts; total = 121.09 crore) | derived by `scripts/prepare_reference_data.py` |

`python -m scripts.prepare_reference_data` re-downloads and rebuilds all of these and also writes `data/raw/districts_simplified.geojson` (district polygons from github.com/geohacker/india, GADM-derived; not committed) for exact point-in-district lookups.

Population is projected from 2011 with `WP_POP_PROJECTION_FACTOR` (default 1.18 ≈ RGI Technical Group projection for 2026 ÷ Census 2011, all-India). For finer, current numbers plug in **WorldPop 100 m** or **GHSL** grids via `GriddedPopulation` in `app/data/loaders.py`.

## To obtain for a real deployment

| Dataset | Use | Access | Loader |
|---|---|---|---|
| **ERA5** single levels (tp, 2t, 10u, 10v, msl), 1991–2020, India box | Climatological baseline; model training labels | Copernicus CDS account + `~/.cdsapirc` ([how-to](https://cds.climate.copernicus.eu/how-to-api)); `pip install cdsapi` | `load_reanalysis_climatology()` |
| **IMDAA** regional reanalysis (12 km) | Higher-resolution Indian baseline | NCMRWF data portal registration | `load_reanalysis_climatology()` |
| **NCUM / NEPS** forecasts (0–10 days, 23-member NEPS) | Live forecast input | NCMRWF / MoES data request | `load_ensemble_forecast()` |
| ECMWF open ensemble (alternative) | Live forecast input without registration | ECMWF open data (`ecmwf-opendata` package) | `load_ensemble_forecast()` (GRIB2) |
| **IMD** gridded rainfall 0.25° & temperature 1° | Validation of detected events | imdlib (`pip install imdlib`) | `load_imd_gridded_rainfall()` |
| IMD API (warnings, nowcasts) | Link official warnings to events | IMD API registration / IP whitelisting | — (set `official_warning`) |
| **OpenStreetMap** schools, hospitals, fire stations | Real institutions | Overpass Turbo export or Geofabrik India extract (`osmium export`) | `load_osm_assets()` |
| UDISE+ school registry, NHM hospital directory | Capacities and contacts | Education / health department data sharing | CSV → assets |
| Fleet GPS (KSRTC, BMTC, logistics) | Real vehicles heading into zones | Authorised feed (MoU) | replace `_attach_vehicles()` |

### Overpass query for institutions (Bengaluru example)

```
[out:json][timeout:120];
area["name"="Bengaluru"]["boundary"="administrative"]->.a;
( nwr["amenity"~"school|college|university|hospital|clinic|fire_station|police"](area.a);
  nwr["emergency"="ambulance_station"](area.a); );
out center tags;
```
Export as GeoJSON and load with `load_osm_assets("bengaluru_institutions.geojson", city="Bengaluru")`.

## Synthetic data (demo)

`python -m scripts.generate_synthetic_data` writes to `data/synthetic/` (all rows tagged `data_source = synthetic_demo`):

| File | What |
|---|---|
| `forecast_ensemble.npz` | 6 members × 41 steps (0–240 h, 6-hourly) × 125 × 121 grid; precip, t2m, wind, mslp; spatially/temporally correlated noise, ~0.1% missing values, 6 injected moving events + 2 random |
| `climatology_month09.npz` | ERA5-like mean/std per cell |
| `truth_events.json` | ground-truth events (for evaluation) |
| `institutions.geojson` | 832 fictional schools, hospitals, rescue units around 18 cities |
| `vehicles.geojson` | simulated vehicle snapshot |
| `citizens_demo.csv` | 500 fictional opt-in app users (no real personal data, no Aadhaar) |
| `incident_reports.csv` | 120 fictional incident records |

Synthetic data proves the pipeline works; it does **not** prove forecast skill on real weather. Validate with ERA5/IMD hindcasts of documented events (e.g. Bengaluru Sept 2022 floods, Cyclone Fani 2019) before any operational use.
