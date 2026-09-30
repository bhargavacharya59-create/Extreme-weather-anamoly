"""Orchestrates the end-to-end pipeline and holds the latest results in memory.

ingest -> preprocess -> detect -> classify (ML) -> track -> ensemble stats ->
impact zones -> population / assets / vehicles -> alert drafts -> storage
"""
from __future__ import annotations

import datetime as dt
import logging
import math
import os
import threading
import time

import numpy as np

from app.alerts import composer, dispatch
from app.config import settings
from app.data.cities import CITIES, CITY_CODE
from app.data.population import get_population
from app.data.synthetic import (EVENT_SIGNATURE, UNITS, VARIABLES, Grid, climatology, demo_scenario,
                                generate_assets, generate_forecast, random_events)
from app.geo import compass, destination, haversine_km
from app.pipeline import impact as imp
from app.pipeline.detection import detect
from app.pipeline.models import ModelBundle
from app.pipeline.preprocess import standardise
from app.pipeline.tracking import associate, describe, extend
from app.storage import Store, new_id, now_iso

log = logging.getLogger("weatherpulse.service")
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
SEV_RANK = {"Low": 0, "Moderate": 1, "High": 2}
VAR_LABEL = {"precip": "6-hour rainfall", "t2m": "2 m temperature", "wind": "10 m wind speed", "mslp": "sea-level pressure"}
SCENARIO_MONTH = int(os.getenv("WP_SCENARIO_MONTH", 9))


def _fmt_local(t: dt.datetime) -> str:
    return t.astimezone(IST).strftime("%a %d %b, %H:%M IST")


def _issue_time() -> dt.datetime:
    now = dt.datetime.now(dt.timezone.utc)
    return now.replace(hour=(now.hour // 6) * 6, minute=0, second=0, microsecond=0)


def _place(lat: float, lon: float) -> dict:
    best, bd = None, 1e9
    for name, state, clat, clon, *_ in CITIES:
        d = float(haversine_km(lat, lon, clat, clon))
        if d < bd:
            best, bd = (name, state), d
    pop = get_population()
    district, dstate, dd = None, None, 1e9
    if len(pop.districts):
        i = int(pop._district_index(np.array([lat]), np.array([lon]))[0])
        row = pop.districts.iloc[i]
        district, dstate = row["district"], row["state"]
        dd = float(haversine_km(lat, lon, row["lat"], row["lon"]))
    if bd <= 25:
        label = f"{best[0]}, {best[1]}"
    elif bd <= 60:
        label = f"{best[0]} outskirts ({compass(_brg(best, lat, lon))}), {best[1]}"
    elif dd <= 90 and district:
        label = f"{district} district, {dstate}"
    else:
        label = f"{round(bd)} km {compass(_brg(best, lat, lon))} of {best[0]}"
    return {"label": label, "nearest_city": best[0], "city_distance_km": round(bd, 1), "district": district, "state": dstate or best[1]}


def _brg(best, lat, lon):
    from app.geo import bearing_deg
    c = next(c for c in CITIES if c[0] == best[0])
    return float(bearing_deg(c[2], c[3], lat, lon))


class Pipeline:
    def __init__(self):
        settings.ensure_dirs()
        self.store = Store()
        self.models = ModelBundle.load()
        self.lock = threading.Lock()
        self.state: dict | None = None
        self.status = "idle"   # idle | training | running | ready
        self.assets = generate_assets()
        self.asset_by_id = {a["id"]: a for a in self.assets}

    # ------------------------------------------------------------ run
    def run(self, seed: int | None = None, extra_random: int = 2) -> dict:
        with self.lock:
            t0 = time.time()
            self.status = "running" if self.state is None else self.status
            seed = settings.default_seed if seed is None else seed
            grid = Grid()
            month = SCENARIO_MONTH
            truth = demo_scenario() + random_events(np.random.default_rng(seed), extra_random, month, grid, prefix="EV-X")
            bundle = generate_forecast(grid, month, truth, seed=seed)
            clim = climatology(grid, month)
            pre = standardise(bundle, clim)
            objs = self.models.annotate(detect(bundle, pre))
            tracks = associate(objs, settings.step_hours)
            issue = _issue_time()
            run_id = f"RUN-{issue.strftime('%Y%m%d%H')}-{seed}"

            events = []
            counters: dict = {}
            for tr in tracks:
                pts = [p for p in tr.points if p.type != "noise"]
                peak = tr.peak
                if len(pts) < 3 or (SEV_RANK[peak.severity] < 1 and peak.ens_prob < 0.5):
                    continue
                ev = self._build_event(tr, peak, issue, grid, bundle, counters)
                events.append(ev)

            events.sort(key=lambda e: (-SEV_RANK[e["severity"]], e["window"]["start_lead_h"]))
            self._attach_vehicles(events, seed)
            summary = self._summary(events)
            run = {
                "run_id": run_id, "issue_time": issue.isoformat(), "issue_time_local": _fmt_local(issue),
                "provider": "Synthetic NEPS-like ensemble", "data_mode": "synthetic_demo",
                "params": {"seed": seed, "month": month, "members": settings.ensemble_members,
                           "grid_res_deg": settings.grid_res, "max_lead_h": settings.max_lead_hours,
                           "z_threshold": settings.z_threshold},
                "qc": pre.qc, "summary": summary,
                "model_version": f"wp-{self.models.trained_at or 'untrained'}",
                "model_metrics": {k: v for k, v in self.models.metrics.items() if k != "type_report"},
                "n_objects": len(objs), "n_tracks": len(tracks), "runtime_s": None,
                "truth": [t.to_dict() for t in truth],
            }
            self.state = {"run": run, "events": events, "bundle": bundle, "clim": clim, "pre": pre, "grid": grid}
            self._draft_alerts(run, events)
            self._rescue_orders(events)
            try:
                from app.accounts import get_accounts
                get_accounts().seed_drivers(events)
            except Exception as e:  # accounts are optional for the pipeline itself
                log.warning("driver account seeding failed: %s", e)
            run["runtime_s"] = round(time.time() - t0, 2)
            self.store.save_run(run, events)
            self.status = "ready"
            log.info("pipeline run %s: %d events in %.1fs", run_id, len(events), run["runtime_s"])
            return run

    # ------------------------------------------------------------ events
    def _build_event(self, tr, peak, issue, grid, bundle, counters) -> dict:
        mot = describe(tr)
        etype = tr.type
        pts_out = []
        for p in tr.points:
            if p.type == "noise":
                continue
            sub = [q for q in tr.points if q.lead_h <= p.lead_h]
            m = describe(type(tr)(id=tr.id, points=sub)) if len(sub) >= 2 else mot
            zone = imp.zone_geometry(p.lat, p.lon, p.severity_score, m["speed_kmh"], m["heading_deg"], p.spread_km)
            pop = imp.population_by_ring(zone)
            assets = imp.assets_in_zone(zone, self.assets)
            counts = {k: sum(1 for a in assets if a["kind"] == k) for k in ("school", "hospital", "rescue_team")}
            valid = issue + dt.timedelta(hours=p.lead_h)
            pts_out.append({
                "lead_h": p.lead_h, "valid_time": valid.isoformat(), "valid_local": _fmt_local(valid),
                "lat": round(p.lat, 4), "lon": round(p.lon, 4),
                "peak_lat": round(p.peak_lat, 4), "peak_lon": round(p.peak_lon, 4),
                "type": p.type, "type_proba": p.type_proba, "severity": p.severity, "severity_score": p.severity_score,
                "probability": round(p.ens_prob, 3), "anomaly_score": p.anomaly_score,
                "uncertainty_km": round(p.spread_km, 1), "area_km2": round(p.area_km2),
                "values": p.values, "z": p.z_peak, "footprint": p.footprint, "member_centroids": p.member_centroids,
                "speed_kmh": m["speed_kmh"], "heading_deg": m["heading_deg"],
                "zone": zone,
                "impact": {"population": {k: pop[k] for k in ("high", "moderate", "low", "total")},
                           "counts": {**counts, "vehicles_toward": 0}},
            })
        # Headline time step = highest impact: among steps within one severity level of the
        # strongest, the one exposing the most people (ties -> stronger anomaly).
        top = max(SEV_RANK[q["severity"]] for q in pts_out)
        cands = [q for q in pts_out if SEV_RANK[q["severity"]] >= top - 1]
        peak_pt = max(cands, key=lambda q: (q["impact"]["population"]["total"] * (1 + SEV_RANK[q["severity"]]), q["severity_score"]))
        place = _place(peak_pt["lat"], peak_pt["lon"])
        code = CITY_CODE.get(place["nearest_city"], place["nearest_city"][:3].upper()) if place["city_distance_km"] < 400 else "SEA"
        counters[code] = counters.get(code, 0) + 1
        eid = f"WX-{code}-{counters[code]:04d}"
        # full detail for the peak point
        full_pop = imp.population_by_ring(peak_pt["zone"])
        peak_assets = imp.assets_in_zone(peak_pt["zone"], self.assets)
        peak_pt["impact"]["population"] = full_pop
        peak_pt["impact"]["assets"] = peak_assets
        high_or_mod = [q for q in pts_out if SEV_RANK[q["severity"]] >= 1] or pts_out
        start_lead, end_lead = high_or_mod[0]["lead_h"], high_or_mod[-1]["lead_h"]
        dom_var = max(VARIABLES, key=lambda v: abs(peak.z_peak[v]) * (1 if EVENT_SIGNATURE.get(etype, {}).get(v) else 0.3))
        zdom = peak.z_peak[dom_var]
        predicted = extend(tr, self.models, settings.step_hours)
        for q in predicted:
            q["valid_local"] = _fmt_local(issue + dt.timedelta(hours=q["lead_h"]))
        ev = {
            "id": eid, "track_id": tr.id, "type": etype,
            "type_confidence": round(float(np.mean([q["type_proba"].get(etype, 0) for q in pts_out if q["type_proba"]] or [0])), 3),
            "severity": peak_pt["severity"], "severity_score": peak_pt["severity_score"],
            "probability": peak_pt["probability"], "anomaly_score": peak_pt["anomaly_score"],
            "place": place["label"], "location": place,
            "window": {"start_lead_h": start_lead, "end_lead_h": end_lead,
                       "start": (issue + dt.timedelta(hours=start_lead)).isoformat(),
                       "end": (issue + dt.timedelta(hours=end_lead)).isoformat(),
                       "start_local": _fmt_local(issue + dt.timedelta(hours=start_lead)),
                       "end_local": _fmt_local(issue + dt.timedelta(hours=end_lead))},
            "first_lead_h": pts_out[0]["lead_h"], "last_lead_h": pts_out[-1]["lead_h"],
            "motion": mot, "peak": peak_pt, "track": pts_out, "predicted": predicted,
            "why": {
                "variable": dom_var, "label": VAR_LABEL[dom_var], "z": round(zdom, 2),
                "value": peak.values[dom_var], "unit": UNITS[dom_var],
                "text": (f"{VAR_LABEL[dom_var].capitalize()} is {abs(zdom):.1f} standard deviations "
                         f"{'above' if zdom > 0 else 'below'} the September baseline for this location "
                         f"({peak.values[dom_var]} {UNITS[dom_var]}). Detected in {len(pts_out)} forecast steps; "
                         f"classifier confidence {peak_pt['type_proba'].get(etype, 0):.2f}, anomaly score {peak_pt['anomaly_score']:.2f}."),
            },
            "data_source": "synthetic_demo", "official_warning": False,
            "status": "active",
        }
        ev["summary"] = composer.situation_summary(ev, use_ai=settings.gemini_in_pipeline)
        return ev

    def _attach_vehicles(self, events, seed):
        """Simulated vehicle positions at each event's peak valid time."""
        rng = np.random.default_rng(seed + 99)
        kinds = [("bus", 30, 50, "BUS"), ("car", 30, 65, "CAR"), ("truck", 25, 50, "TRK"), ("two_wheeler", 20, 40, "TWW")]
        for ev in events:
            z = ev["peak"]["zone"]
            clat, clon = z["center"][1], z["center"][0]
            code = ev["id"].split("-")[1]
            vehicles = []
            if ev["peak"]["impact"]["population"]["total"] <= 0:   # open sea: no road traffic
                ev["vehicles"] = {"tracked": 0, "all": [], "toward": []}
                continue
            n = 70 if ev["location"]["city_distance_km"] < 60 else 25
            for i in range(n):
                k, vmin, vmax, pre = kinds[int(rng.integers(len(kinds)))]
                dist = float(rng.uniform(3, 38))
                ang = float(rng.uniform(0, 360))
                lat, lon = destination(clat, clon, ang, dist)
                toward = (ang + 180) % 360
                heading = (toward + rng.normal(0, 12)) % 360 if rng.random() < 0.35 else float(rng.uniform(0, 360))
                vehicles.append({"id": f"{pre}-{code}-{i + 1:03d}", "kind": k, "lat": round(lat, 5), "lon": round(lon, 5),
                                 "heading_deg": round(float(heading), 1), "speed_kmh": round(float(rng.uniform(vmin, vmax)), 1),
                                 "operator": "BMTC" if (k == "bus" and code == "BLR") else ("State transport" if k == "bus" else "Private"),
                                 "data_source": "simulated"})
            toward_list = imp.vehicles_toward(z, vehicles)
            ev["vehicles"] = {"tracked": len(vehicles), "all": vehicles, "toward": toward_list}
            ev["peak"]["impact"]["counts"]["vehicles_toward"] = len(toward_list)

    def _summary(self, events) -> dict:
        by_sev = {s: sum(1 for e in events if e["severity"] == s) for s in ("High", "Moderate", "Low")}
        by_type: dict = {}
        for e in events:
            by_type[e["type"]] = by_type.get(e["type"], 0) + 1
        pop = sum(e["peak"]["impact"]["population"]["total"] for e in events)
        return {"active": len(events), "by_severity": by_sev, "by_type": by_type, "population_exposed": pop,
                "schools": sum(e["peak"]["impact"]["counts"]["school"] for e in events),
                "hospitals": sum(e["peak"]["impact"]["counts"]["hospital"] for e in events),
                "rescue_teams": sum(e["peak"]["impact"]["counts"]["rescue_team"] for e in events),
                "vehicles_toward": sum(e["peak"]["impact"]["counts"]["vehicles_toward"] for e in events),
                "vehicles_tracked": sum(e.get("vehicles", {}).get("tracked", 0) for e in events)}

    # ------------------------------------------------------------ alerts
    def draft_alert(self, ev: dict, role: str, language: str = "en", created_by: str = "system",
                    use_ai: bool = True) -> dict:
        d = composer.draft(ev, role, language, use_ai=use_ai)
        imp_ = ev["peak"]["impact"]
        recipients = {
            "official": 1,
            "school": imp_["counts"]["school"], "hospital": imp_["counts"]["hospital"],
            "rescue": imp_["counts"]["rescue_team"],
            "citizen": imp_["population"]["total"],
            "traveller": imp_["counts"]["vehicles_toward"],
        }[role]
        a = {
            "alert_id": new_id("AL"), "event_id": ev["id"], "run_id": self.state["run"]["run_id"], "role": role,
            "title": d["title"], "message": d["body"], "language": language,
            "channels": dispatch.ROLE_CHANNELS[role], "recipients": int(recipients),
            # officials & travellers (standing order) go out automatically; the rest need approval
            "requires_approval": role not in ("official", "traveller"),
            "approval_status": "draft", "generated_by": d["generated_by"], "created_at": now_iso(),
            "target": {"severity": ev["severity"], "place": ev["place"], "created_by": created_by},
        }
        self.store.save_alert(a)
        if not a["requires_approval"]:
            self.approve_alert(a["alert_id"], "standing-order" if role == "traveller" else "auto")
        return self.store.alert(a["alert_id"])

    def _draft_alerts(self, run, events):
        existing = {(a["event_id"], a["role"]) for a in self.store.alerts(run_id=run["run_id"])}
        for ev in events:
            if SEV_RANK[ev["severity"]] < 1:
                continue
            for role in ("official", "school", "hospital", "rescue", "citizen", "traveller"):
                if (ev["id"], role) in existing:
                    continue
                if role in ("school", "hospital", "rescue") and not ev["peak"]["impact"]["counts"].get(
                        {"school": "school", "hospital": "hospital", "rescue": "rescue_team"}[role]):
                    continue
                if role == "traveller" and not ev["peak"]["impact"]["counts"]["vehicles_toward"]:
                    continue
                if role == "citizen" and ev["peak"]["impact"]["population"]["total"] <= 0:
                    continue   # over open sea: nobody to warn
                self.draft_alert(ev, role, use_ai=settings.gemini_in_pipeline)

    def recipients_for(self, alert: dict) -> list[dict]:
        ev = self.event(alert["event_id"])
        if not ev:
            return []
        role = alert["role"]
        if role == "official":
            return [{"id": "EOC", "name": f"District EOC ({ev['location'].get('district') or ev['place']})",
                     "phone": "+910000000000", "email": "eoc@example.org"}]
        if role in ("school", "hospital", "rescue"):
            kind = {"school": "school", "hospital": "hospital", "rescue": "rescue_team"}[role]
            return [{"id": a["id"], "name": a["name"], "phone": "+91000000" + a["id"][-4:].replace("-", "0"),
                     "email": a["contact"]} for a in ev["peak"]["impact"].get("assets", []) if a["kind"] == kind]
        if role == "traveller":
            return [{"id": v["id"], "name": v["id"]} for v in ev.get("vehicles", {}).get("toward", [])]
        return [{"id": "cell-broadcast", "name": f"Cell broadcast · {alert['recipients']:,} residents"}]

    def approve_alert(self, alert_id: str, user: str) -> dict | None:
        a = self.store.alert(alert_id)
        if not a:
            return None
        a["approval_status"] = "approved"
        a["approved_by"], a["approved_at"] = user, now_iso()
        self.store.save_alert(a)
        counts = dispatch.deliver(self.store, a, self.recipients_for(a))
        a["approval_status"] = "sent"
        self.store.save_alert(a)
        self.store.audit(user, "approve_alert", {"alert_id": alert_id, "delivery": counts})
        return self.store.alert(alert_id)

    def reject_alert(self, alert_id: str, user: str, reason: str = "") -> dict | None:
        a = self.store.alert(alert_id)
        if not a:
            return None
        a["approval_status"] = "rejected"
        a["approved_by"], a["approved_at"] = user, now_iso()
        self.store.save_alert(a)
        self.store.audit(user, "reject_alert", {"alert_id": alert_id, "reason": reason})
        return a

    # ------------------------------------------------------------ rescue
    def _rescue_orders(self, events):
        existing = {o["order_id"] for o in self.store.orders()}
        for ev in events:
            if SEV_RANK[ev["severity"]] < 1 or ev["peak"]["impact"]["population"]["total"] <= 0:
                continue   # pre-position for High and Moderate events that affect people
            teams = [a for a in ev["peak"]["impact"].get("assets", []) if a["kind"] == "rescue_team"]
            if not teams:
                z = ev["peak"]["zone"]
                teams = sorted((a for a in self.assets if a["kind"] == "rescue_team"),
                               key=lambda a: float(haversine_km(a["lat"], a["lon"], z["center"][1], z["center"][0])))[:2]
            for t in teams[:3]:
                oid = f"ORD-{ev['id'].split('-', 1)[1]}-{t['id'].split('-')[-1]}"
                if oid in existing:
                    continue
                z = ev["peak"]["zone"]
                d = float(haversine_km(t["lat"], t["lon"], z["center"][1], z["center"][0]))
                stage_time = dt.datetime.fromisoformat(ev["window"]["start"]) - dt.timedelta(hours=2)
                self.store.upsert_order({
                    "order_id": oid, "event_id": ev["id"], "unit_id": t["id"], "unit_name": t["name"],
                    "status": "issued", "severity": ev["severity"], "type": ev["type"], "place": ev["place"],
                    "stage_at": {"lat": z["center"][1], "lon": z["center"][0]},
                    "stage_by_local": _fmt_local(stage_time), "window": ev["window"],
                    "distance_km": round(d, 1), "drive_min": int(round(d * 1.35 / 35 * 60)),
                    "people_high": ev["peak"]["impact"]["population"]["high"],
                    "priorities": [f"{a['name']} ({a['ring']} risk)" for a in ev["peak"]["impact"].get("assets", [])
                                   if a["kind"] in ("school", "hospital")][:4],
                    "guidance": composer.GUIDANCE.get(ev["type"], {}).get("rescue", []),
                })

    # ------------------------------------------------------------ queries
    def ensure(self):
        if self.state is None:
            self.run()
        return self.state

    def events(self) -> list[dict]:
        return self.ensure()["events"]

    def event(self, eid: str) -> dict | None:
        return next((e for e in self.events() if e["id"] == eid), None)

    def point_at(self, ev: dict, lead_h: int | None) -> dict | None:
        if lead_h is None:
            return ev["peak"]
        if lead_h < ev["track"][0]["lead_h"] - settings.step_hours or lead_h > ev["track"][-1]["lead_h"] + settings.step_hours:
            return None
        return min(ev["track"], key=lambda q: abs(q["lead_h"] - lead_h))

    def weather_series(self, lat: float, lon: float) -> dict:
        st = self.ensure()
        g, b = st["grid"], st["bundle"]
        i = int(np.clip(round((lat - g.lat_min) / g.res), 0, g.shape[0] - 1))
        j = int(np.clip(round((lon - g.lon_min) / g.res), 0, g.shape[1] - 1))
        issue = dt.datetime.fromisoformat(st["run"]["issue_time"])
        out = {"lat": float(g.lats[i]), "lon": float(g.lons[j]), "lead_h": b.lead_hours.tolist(),
               "valid_local": [_fmt_local(issue + dt.timedelta(hours=int(h))) for h in b.lead_hours], "variables": {}}
        for v in VARIABLES:
            a = b.fields[v][:, :, i, j]
            mean_c, std_c = st["clim"][v]
            clim_val = float(mean_c[i, j] ** 3) if v == "precip" else float(mean_c[i, j])
            out["variables"][v] = {"unit": UNITS[v], "label": VAR_LABEL[v],
                                   "mean": np.round(np.nanmean(a, axis=0), 2).tolist(),
                                   "min": np.round(np.nanmin(a, axis=0), 2).tolist(),
                                   "max": np.round(np.nanmax(a, axis=0), 2).tolist(),
                                   "z": np.round(st["pre"].z_mean[v][:, i, j], 2).tolist(),
                                   "climatology": round(clim_val, 2)}
        return out

    def anomaly_grid(self, lead_h: int, var: str = "severity", thr: float = 1.5, stride: int = 1) -> dict:
        from app.pipeline.detection import severity_signal
        st = self.ensure()
        b, g = st["bundle"], st["grid"]
        ti = int(np.argmin(np.abs(b.lead_hours - lead_h)))
        z = severity_signal({k: v[ti:ti + 1] for k, v in st["pre"].z_mean.items()})[0] if var == "severity" else st["pre"].z_mean[var][ti]
        zz = z[::stride, ::stride]
        la, lo = g.LAT[::stride, ::stride], g.LON[::stride, ::stride]
        m = np.abs(zz) >= thr
        feats = [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [float(x), float(y)]},
                  "properties": {"z": round(float(v), 2)}} for x, y, v in zip(lo[m], la[m], zz[m])]
        return {"type": "FeatureCollection", "lead_h": int(b.lead_hours[ti]), "variable": var, "features": feats}


_pipeline: Pipeline | None = None


def get_pipeline() -> Pipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = Pipeline()
    return _pipeline
