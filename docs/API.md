# API reference (v1)

Base URL `http://localhost:8000/api/v1`. Interactive docs at `/docs` (Swagger). All routes except `/auth/*` and `/health` need `Authorization: Bearer <token>` from `POST /auth/login`.

| Method | Path | Roles | Purpose |
|---|---|---|---|
| POST | `/auth/login` | public | login |
| GET | `/auth/me` | public | me |
| GET | `/auth/demo-accounts` | public | demo accounts |
| GET | `/health` | public | health |
| GET | `/dashboard/summary` | public | dashboard summary |
| GET | `/weather/forecast` | public | weather forecast |
| GET | `/weather/anomaly-grid` | public | weather grid |
| GET | `/anomalies` | public | anomalies |
| GET | `/anomalies/{event_id}` | public | anomaly |
| GET | `/anomalies/{event_id}/trajectory` | public | trajectory |
| GET | `/anomalies/{event_id}/impact` | public | impact |
| GET | `/maps/risk-zones` | public | risk zones |
| GET | `/maps/tracks` | public | tracks |
| GET | `/maps/assets` | public | assets geojson |
| GET | `/maps/wards` | public | wards |
| GET | `/maps/vehicles` | public | vehicles geojson |
| GET | `/population/districts` | public | districts |
| GET | `/population/at` | public | population at |
| GET | `/vehicles` | public | vehicles |
| GET | `/traveller/status` | public | traveller status |
| GET | `/institutions` | public | institutions |
| GET | `/institutions/me` | public | my institution |
| GET | `/institutions/{asset_id}/status` | public | institution status |
| POST | `/institutions/{asset_id}/acknowledge` | public | acknowledge |
| POST | `/institutions/{asset_id}/checklist` | public | checklist |
| GET | `/citizen/status` | public | citizen status |
| GET | `/rescue/orders` | public | rescue orders |
| POST | `/rescue/orders/{order_id}/status` | public | order status |
| GET | `/alerts` | public | alerts |
| GET | `/alerts/feed` | public | Sent alerts visible to the signed-in role (in-app channel). |
| POST | `/alerts/draft` | public | alert draft |
| PATCH | `/alerts/{alert_id}` | public | alert edit |
| POST | `/alerts/{alert_id}/approve` | public | alert approve |
| POST | `/alerts/{alert_id}/reject` | public | alert reject |
| GET | `/alerts/{alert_id}/deliveries` | public | alert deliveries |
| POST | `/copilot/ask` | public | copilot ask |
| GET | `/reports` | public | reports |
| GET | `/reports/events.csv` | public | report csv |
| GET | `/reports/situation.pdf` | public | report run pdf |
| GET | `/reports/{event_id}.pdf` | public | report event pdf |
| GET | `/analytics` | public | analytics |
| GET | `/settings/status` | public | settings status |
| POST | `/pipeline/run` | public | pipeline run |
| POST | `/feedback` | public | feedback |
| POST | `/models/retrain` | public | retrain |
| GET | `/models/retrain` | public | retrain status |
