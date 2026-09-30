"""SQLite persistence (stdlib). Schema mirrors the PostgreSQL/PostGIS design in
docs/ARCHITECTURE.md (db/schema_postgis.sql) so it can be swapped later.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid

from app.config import settings

_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS forecast_runs (
  run_id TEXT PRIMARY KEY, created_at TEXT, issue_time TEXT, provider TEXT,
  data_mode TEXT, params TEXT, summary TEXT, model_version TEXT);
CREATE TABLE IF NOT EXISTS anomaly_events (
  event_id TEXT, run_id TEXT, anomaly_type TEXT, severity TEXT,
  first_seen TEXT, last_seen TEXT, status TEXT, data TEXT,
  PRIMARY KEY (event_id, run_id));
CREATE TABLE IF NOT EXISTS alerts (
  alert_id TEXT PRIMARY KEY, event_id TEXT, run_id TEXT, role TEXT, title TEXT, message TEXT,
  language TEXT, channels TEXT, recipients INTEGER, approval_status TEXT, requires_approval INTEGER,
  generated_by TEXT, created_at TEXT, approved_by TEXT, approved_at TEXT, target TEXT);
CREATE TABLE IF NOT EXISTS notification_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, alert_id TEXT, recipient_group TEXT, channel TEXT,
  recipient TEXT, delivery_status TEXT, detail TEXT, timestamp TEXT);
CREATE TABLE IF NOT EXISTS acknowledgements (
  id INTEGER PRIMARY KEY AUTOINCREMENT, alert_id TEXT, asset_id TEXT, user_id TEXT, note TEXT, timestamp TEXT);
CREATE TABLE IF NOT EXISTS checklist (
  asset_id TEXT, item TEXT, done INTEGER, updated_at TEXT, PRIMARY KEY (asset_id, item));
CREATE TABLE IF NOT EXISTS rescue_orders (
  order_id TEXT PRIMARY KEY, event_id TEXT, unit_id TEXT, status TEXT, data TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS feedback (
  id INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT, run_id TEXT, observed INTEGER,
  observed_type TEXT, observed_severity TEXT, notes TEXT, features TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, action TEXT, detail TEXT, timestamp TEXT);
"""


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"


class Store:
    def __init__(self, path=None):
        settings.ensure_dirs()
        self.path = str(path or settings.db_path)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        with _lock:
            self.conn.executescript(SCHEMA)
            self.conn.commit()

    def execute(self, sql, params=()):
        with _lock:
            cur = self.conn.execute(sql, params)
            self.conn.commit()
            return cur

    def query(self, sql, params=()) -> list[dict]:
        with _lock:
            return [dict(r) for r in self.conn.execute(sql, params).fetchall()]

    # ---- runs & events
    def save_run(self, run: dict, events: list[dict]):
        self.execute("INSERT OR REPLACE INTO forecast_runs VALUES (?,?,?,?,?,?,?,?)", (
            run["run_id"], now_iso(), run["issue_time"], run["provider"], run["data_mode"],
            json.dumps(run.get("params", {})), json.dumps(run.get("summary", {})), run.get("model_version", "")))
        for e in events:
            self.execute("INSERT OR REPLACE INTO anomaly_events VALUES (?,?,?,?,?,?,?,?)", (
                e["id"], run["run_id"], e["type"], e["severity"], e["window"]["start"], e["window"]["end"],
                "active", json.dumps(e, default=str)))

    def runs(self, limit=20):
        rows = self.query("SELECT * FROM forecast_runs ORDER BY created_at DESC LIMIT ?", (limit,))
        for r in rows:
            r["params"] = json.loads(r["params"] or "{}")
            r["summary"] = json.loads(r["summary"] or "{}")
        return rows

    def event_history(self, limit=200):
        return self.query("SELECT event_id, run_id, anomaly_type, severity, first_seen, last_seen, status "
                          "FROM anomaly_events ORDER BY first_seen DESC LIMIT ?", (limit,))

    # ---- alerts
    def save_alert(self, a: dict):
        self.execute("INSERT OR REPLACE INTO alerts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            a["alert_id"], a["event_id"], a["run_id"], a["role"], a["title"], a["message"], a["language"],
            json.dumps(a["channels"]), a["recipients"], a["approval_status"], int(a["requires_approval"]),
            a["generated_by"], a["created_at"], a.get("approved_by"), a.get("approved_at"), json.dumps(a.get("target", {}))))

    def alerts(self, run_id=None, status=None, role=None, event_id=None) -> list[dict]:
        sql, p = "SELECT * FROM alerts WHERE 1=1", []
        for col, val in (("run_id", run_id), ("approval_status", status), ("role", role), ("event_id", event_id)):
            if val:
                sql += f" AND {col}=?"
                p.append(val)
        rows = self.query(sql + " ORDER BY created_at DESC", tuple(p))
        for r in rows:
            r["channels"] = json.loads(r["channels"] or "[]")
            r["target"] = json.loads(r["target"] or "{}")
            r["requires_approval"] = bool(r["requires_approval"])
        return rows

    def alert(self, alert_id):
        rows = [r for r in self.alerts() if r["alert_id"] == alert_id]
        return rows[0] if rows else None

    def log_delivery(self, alert_id, group, channel, recipient, status, detail=""):
        self.execute("INSERT INTO notification_logs (alert_id, recipient_group, channel, recipient, delivery_status, detail, timestamp) "
                     "VALUES (?,?,?,?,?,?,?)", (alert_id, group, channel, recipient, status, detail, now_iso()))

    def deliveries(self, alert_id=None, limit=500):
        if alert_id:
            return self.query("SELECT * FROM notification_logs WHERE alert_id=? ORDER BY id DESC", (alert_id,))
        return self.query("SELECT * FROM notification_logs ORDER BY id DESC LIMIT ?", (limit,))

    # ---- institutions
    def acknowledge(self, alert_id, asset_id, user_id, note=""):
        self.execute("INSERT INTO acknowledgements (alert_id, asset_id, user_id, note, timestamp) VALUES (?,?,?,?,?)",
                     (alert_id, asset_id, user_id, note, now_iso()))

    def acknowledgements(self, asset_id=None):
        if asset_id:
            return self.query("SELECT * FROM acknowledgements WHERE asset_id=? ORDER BY id DESC", (asset_id,))
        return self.query("SELECT * FROM acknowledgements ORDER BY id DESC")

    def set_checklist(self, asset_id, item, done):
        self.execute("INSERT OR REPLACE INTO checklist VALUES (?,?,?,?)", (asset_id, item, int(done), now_iso()))

    def checklist(self, asset_id) -> dict:
        return {r["item"]: bool(r["done"]) for r in self.query("SELECT * FROM checklist WHERE asset_id=?", (asset_id,))}

    # ---- rescue
    def upsert_order(self, o: dict):
        self.execute("INSERT OR REPLACE INTO rescue_orders VALUES (?,?,?,?,?,?)",
                     (o["order_id"], o["event_id"], o["unit_id"], o["status"], json.dumps(o, default=str), now_iso()))

    def orders(self, unit_id=None):
        sql, p = "SELECT * FROM rescue_orders", ()
        if unit_id:
            sql, p = sql + " WHERE unit_id=?", (unit_id,)
        out = []
        for r in self.query(sql, p):
            d = json.loads(r["data"])
            d["status"] = r["status"]
            out.append(d)
        return out

    def set_order_status(self, order_id, status, note=""):
        rows = self.query("SELECT data FROM rescue_orders WHERE order_id=?", (order_id,))
        if not rows:
            return None
        d = json.loads(rows[0]["data"])
        d["status"], d["status_note"] = status, note
        self.upsert_order(d)
        return d

    # ---- feedback & audit
    def add_feedback(self, fb: dict):
        self.execute("INSERT INTO feedback (event_id, run_id, observed, observed_type, observed_severity, notes, features, created_at) "
                     "VALUES (?,?,?,?,?,?,?,?)", (fb["event_id"], fb.get("run_id"), int(fb["observed"]), fb.get("observed_type"),
                                                  fb.get("observed_severity"), fb.get("notes", ""), json.dumps(fb.get("features", [])), now_iso()))

    def feedback(self):
        rows = self.query("SELECT * FROM feedback ORDER BY id DESC")
        for r in rows:
            r["features"] = json.loads(r["features"] or "[]")
        return rows

    def audit(self, user_id, action, detail):
        self.execute("INSERT INTO audit_log (user_id, action, detail, timestamp) VALUES (?,?,?,?)",
                     (user_id, action, json.dumps(detail, default=str)[:4000], now_iso()))

    def audit_log(self, limit=200):
        return self.query("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))
