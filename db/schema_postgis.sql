-- PostgreSQL + PostGIS schema (production). The prototype uses SQLite with the same tables (backend/app/storage.py).
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE forecast_runs (
  run_id TEXT PRIMARY KEY, provider TEXT, model TEXT, issue_time TIMESTAMPTZ, data_mode TEXT,
  params JSONB, summary JSONB, model_version TEXT, created_at TIMESTAMPTZ DEFAULT now());

CREATE TABLE anomaly_events (
  event_id TEXT, run_id TEXT REFERENCES forecast_runs, anomaly_type TEXT, severity TEXT,
  first_seen TIMESTAMPTZ, last_seen TIMESTAMPTZ, status TEXT, probability REAL, data JSONB,
  PRIMARY KEY (event_id, run_id));

CREATE TABLE event_trajectories (
  event_id TEXT, run_id TEXT, valid_time TIMESTAMPTZ, lead_h INT, geom GEOMETRY(Point, 4326),
  severity TEXT, speed_kmh REAL, heading_deg REAL, uncertainty_km REAL);
CREATE INDEX ON event_trajectories USING GIST (geom);

CREATE TABLE risk_zones (
  event_id TEXT, run_id TEXT, valid_time TIMESTAMPTZ, risk_category TEXT, geom GEOMETRY(Polygon, 4326));
CREATE INDEX ON risk_zones USING GIST (geom);

CREATE TABLE infrastructure_assets (
  asset_id TEXT PRIMARY KEY, asset_type TEXT, name TEXT, capacity INT, contact TEXT, source TEXT,
  geom GEOMETRY(Point, 4326));
CREATE INDEX ON infrastructure_assets USING GIST (geom);

CREATE TABLE population_units (
  unit_id TEXT PRIMARY KEY, unit_type TEXT, name TEXT, state TEXT, population_2011 BIGINT, area_km2 REAL,
  source TEXT, geom GEOMETRY(MultiPolygon, 4326));
CREATE INDEX ON population_units USING GIST (geom);

CREATE TABLE impact_estimates (
  event_id TEXT, run_id TEXT, valid_time TIMESTAMPTZ, population_high BIGINT, population_moderate BIGINT,
  population_low BIGINT, school_count INT, hospital_count INT, vehicles_toward INT, methodology TEXT);

CREATE TABLE alerts (
  alert_id TEXT PRIMARY KEY, event_id TEXT, run_id TEXT, role TEXT, title TEXT, message TEXT, language TEXT,
  channels TEXT[], recipients INT, approval_status TEXT, requires_approval BOOLEAN, generated_by TEXT,
  created_at TIMESTAMPTZ DEFAULT now(), approved_by TEXT, approved_at TIMESTAMPTZ);

CREATE TABLE notification_logs (
  id BIGSERIAL PRIMARY KEY, alert_id TEXT REFERENCES alerts, recipient_group TEXT, channel TEXT,
  recipient TEXT, delivery_status TEXT, detail TEXT, timestamp TIMESTAMPTZ DEFAULT now());

CREATE TABLE users (user_id TEXT PRIMARY KEY, role TEXT, organization_id TEXT, authentication_reference TEXT);
CREATE TABLE audit_log (id BIGSERIAL PRIMARY KEY, user_id TEXT, action TEXT, detail JSONB, timestamp TIMESTAMPTZ DEFAULT now());
