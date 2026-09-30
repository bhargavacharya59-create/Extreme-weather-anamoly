"""REST API v1 (FastAPI). All routes except /auth/* and /health need a bearer token."""
from __future__ import annotations

import math
import threading

import numpy as np
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel

from app import auth
from app.alerts import composer, gemini
from app.config import settings
from app.copilot import Copilot
from app.data.population import PROJECTION_FACTOR, get_population
from app.geo import bearing_deg, destination, haversine_km, points_in_polygon
from app.pipeline import impact as imp
from app.reports import event_pdf, events_csv, run_pdf
from app.service import SEV_RANK, get_pipeline

router = APIRouter(prefix="/api/v1")


# ------------------------------------------------------------------ auth
def current_user(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Sign in required")
    user = auth.verify_token(authorization.split(" ", 1)[1])
    if not user:
        raise HTTPException(401, "Session expired, sign in again")
    return user


def require(*roles):
    def dep(user: dict = Depends(current_user)):
        if roles and user["role"] not in roles:
            raise HTTPException(403, f"Requires role: {', '.join(roles)}")
        return user
    return dep


OFFICIAL = require("official")


class LoginBody(BaseModel):
    username: str | None = None
    email: str | None = None        # backwards compatible field name
    password: str


@router.post("/auth/login")
def login(body: LoginBody):
    res = auth.login(body.username or body.email or "", body.password)
    if not res:
        raise HTTPException(401, "Wrong username or password")
    return res


class RegisterBody(BaseModel):
    name: str
    phone: str
    password: str
    email: str | None = None
    locality_id: str | None = None   # from /auth/localities
    lat: float | None = None         # or the phone's GPS position
    lon: float | None = None


def _localities():
    from app.data.cities import CITIES
    pop = get_population()
    out = []
    for w in pop.wards:
        ring = np.asarray(w["polys"][0])
        out.append({"id": f"W{w['ward_no']}", "label": f"{w['ward_name'].replace(' Ward', '')}, Bengaluru",
                    "group": "Bengaluru (BBMP wards)", "lat": round(float(ring[:, 1].mean()), 5), "lon": round(float(ring[:, 0].mean()), 5)})
    for name, state, lat, lon, *_ in CITIES:
        out.append({"id": f"C-{name}", "label": f"{name}, {state}", "group": "Cities", "lat": lat, "lon": lon})
    return sorted(out, key=lambda x: (x["group"] != "Bengaluru (BBMP wards)", x["label"]))


@router.get("/auth/localities")
def localities():
    return _localities()


@router.post("/auth/register")
def register(body: RegisterBody):
    from app.accounts import get_accounts
    if body.lat is not None and body.lon is not None:
        lat, lon, label = body.lat, body.lon, "My location"
    else:
        loc = next((l for l in _localities() if l["id"] == body.locality_id), None)
        if not loc:
            raise HTTPException(400, "Choose your area")
        lat, lon, label = loc["lat"], loc["lon"], loc["label"]
    try:
        u = get_accounts().register_citizen(body.name, body.phone, body.password, body.email, lat, lon, label)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return auth.session_for(u)


@router.get("/auth/me")
def me(user: dict = Depends(current_user)):
    return user


@router.get("/auth/directory")
def directory(role: str, q: str = "", limit: int = 30):
    """Names for the sign-in autocomplete (institutions, rescue units, buses)."""
    from app.accounts import get_accounts
    if role not in ("institution", "rescue", "traveller"):
        raise HTTPException(400, "Unknown role")
    return [{"username": r["username"], "title": r["title"]} for r in get_accounts().directory(role, q, min(limit, 100))]


@router.get("/auth/quick-access")
def quick_access():
    """One ready-to-use demo login per role (for judges); full list via scripts/export_accounts.py."""
    from app.accounts import GOVT_USERNAME, demo_password, get_accounts
    p = get_pipeline()
    acc = get_accounts()
    out = [{"role": "official", "label": "Government official", "username": GOVT_USERNAME, "password": demo_password(GOVT_USERNAME)}]
    if p.state:
        for kind, role, label in (("school", "institution", "School / college"), ("hospital", "institution", "Hospital")):
            best = None
            for e in p.events():
                for a in e["peak"]["impact"].get("assets", []):
                    if a["kind"] == kind and (best is None or ({"high": 0, "moderate": 1, "low": 2}[a["ring"]], a["distance_km"]) < best[0]):
                        best = (({"high": 0, "moderate": 1, "low": 2}[a["ring"]], a["distance_km"]), a)
            if best:
                out.append({"role": role, "label": label, "username": best[1]["name"], "password": demo_password(best[1]["name"])})
        orders = sorted(p.store.orders(), key=lambda o: "Bengaluru" not in o["place"])
        if orders:
            unit = p.asset_by_id.get(orders[0]["unit_id"])
            if unit:
                out.append({"role": "rescue", "label": "Rescue team", "username": unit["name"], "password": demo_password(unit["name"])})
        buses = [(e, v) for e in p.events() for v in e.get("vehicles", {}).get("toward", []) if v["kind"] == "bus"]
        buses.sort(key=lambda c: (c[0]["location"]["nearest_city"] != "Bengaluru", c[1]["status"] != "approaching"))
        if buses and acc.find_login(buses[0][1]["id"]):
            out.append({"role": "traveller", "label": "Bus driver", "username": buses[0][1]["id"], "password": demo_password(buses[0][1]["id"])})
    out.append({"role": "citizen", "label": "Citizen (sample)", "username": "9000000001", "password": demo_password("citizen-9000000001")})
    return out


@router.get("/health")
def health():
    p = get_pipeline()
    return {"status": "ok", "pipeline": p.status, "run": p.state["run"]["run_id"] if p.state else None, "gemini": gemini.enabled()}


# ------------------------------------------------------------------ helpers
def _p():
    p = get_pipeline()
    if p.state is None and p.status in ("training", "running"):
        raise HTTPException(503, "Starting up: " + ("training the AI models (first start, about a minute)" if p.status == "training" else "running the forecast pipeline"))
    p.ensure()
    return p


def _lite_point(q):
    return {k: q[k] for k in ("lead_h", "valid_local", "lat", "lon", "severity", "severity_score", "probability",
                              "uncertainty_km", "speed_kmh", "heading_deg")} | {
        "people": q["impact"]["population"]["total"]}


def _lite(e):
    pk = e["peak"]
    return {
        "id": e["id"], "type": e["type"], "severity": e["severity"], "severity_score": e["severity_score"],
        "probability": e["probability"], "anomaly_score": e["anomaly_score"], "type_confidence": e["type_confidence"],
        "place": e["place"], "location": e["location"], "window": e["window"], "motion": e["motion"],
        "first_lead_h": e["first_lead_h"], "last_lead_h": e["last_lead_h"],
        "peak": {"lead_h": pk["lead_h"], "valid_local": pk["valid_local"], "lat": pk["lat"], "lon": pk["lon"],
                 "severity": pk["severity"], "uncertainty_km": pk["uncertainty_km"], "values": pk["values"], "z": pk["z"],
                 "population": {k: pk["impact"]["population"][k] for k in ("high", "moderate", "low", "total")},
                 "counts": pk["impact"]["counts"]},
        "track": [_lite_point(q) for q in e["track"]],
        "predicted": e["predicted"], "why": e["why"], "summary": e["summary"],
        "data_source": e["data_source"], "official_warning": e["official_warning"],
    }


def _event_or_404(eid):
    ev = _p().event(eid)
    if not ev:
        raise HTTPException(404, f"Event {eid} not found")
    return ev


def _active_at(ev, lead_h):
    return lead_h is None or (ev["track"][0]["lead_h"] <= lead_h <= ev["track"][-1]["lead_h"])


# ------------------------------------------------------------------ dashboard & weather
@router.get("/dashboard/summary")
def dashboard_summary(lead_h: int | None = None, user: dict = Depends(current_user)):
    p = _p()
    run = p.state["run"]
    evs = [e for e in p.events() if _active_at(e, lead_h)]
    pts = [p.point_at(e, lead_h) or e["peak"] for e in evs]
    pop = [q["impact"]["population"] for q in pts]
    return {
        "run": {k: run[k] for k in ("run_id", "issue_time", "issue_time_local", "provider", "data_mode", "params", "model_version", "runtime_s")},
        "lead_h": lead_h, "active": len(evs),
        "by_severity": {s: sum(1 for q in pts if q["severity"] == s) for s in ("High", "Moderate", "Low")},
        "by_type": {t: sum(1 for e in evs if e["type"] == t) for t in {e["type"] for e in evs}},
        "population": {"high": sum(x["high"] for x in pop), "moderate": sum(x["moderate"] for x in pop),
                       "low": sum(x["low"] for x in pop), "total": sum(x["total"] for x in pop)},
        "schools": sum(q["impact"]["counts"]["school"] for q in pts),
        "hospitals": sum(q["impact"]["counts"]["hospital"] for q in pts),
        "rescue_teams": sum(q["impact"]["counts"]["rescue_team"] for q in pts),
        "vehicles_toward": sum(e["peak"]["impact"]["counts"]["vehicles_toward"] for e in evs),
        "vehicles_tracked": sum(e.get("vehicles", {}).get("tracked", 0) for e in evs),
        "alerts_pending": len(p.store.alerts(run_id=run["run_id"], status="draft")),
        "top_event": evs and max(evs, key=lambda e: (SEV_RANK[e["severity"]], e["peak"]["impact"]["population"]["total"]))["id"] or None,
        "population_source": f"Census of India 2011 (BBMP wards / districts) × {PROJECTION_FACTOR}",
    }


@router.get("/weather/forecast")
def weather_forecast(lat: float, lon: float, user: dict = Depends(current_user)):
    return _p().weather_series(lat, lon)


@router.get("/weather/anomaly-grid")
def weather_grid(lead_h: int = 0, var: str = "severity", thr: float = 1.5, user: dict = Depends(current_user)):
    return _p().anomaly_grid(lead_h, var, thr)


# ------------------------------------------------------------------ anomalies
@router.get("/anomalies")
def anomalies(lead_h: int | None = None, severity: str | None = None, type: str | None = None, user: dict = Depends(current_user)):
    out = []
    for e in _p().events():
        if not _active_at(e, lead_h):
            continue
        if severity and e["severity"].lower() != severity.lower():
            continue
        if type and e["type"] != type:
            continue
        out.append(_lite(e))
    return out


@router.get("/anomalies/{event_id}")
def anomaly(event_id: str, user: dict = Depends(current_user)):
    e = _event_or_404(event_id)
    d = _lite(e)
    d["peak_full"] = {k: v for k, v in e["peak"].items() if k != "member_centroids"}
    return d


@router.get("/anomalies/{event_id}/trajectory")
def trajectory(event_id: str, user: dict = Depends(current_user)):
    e = _event_or_404(event_id)
    return {"event_id": e["id"], "motion": e["motion"],
            "track": [{**_lite_point(q), "member_centroids": q["member_centroids"], "footprint": q["footprint"]} for q in e["track"]],
            "predicted": e["predicted"]}


@router.get("/anomalies/{event_id}/impact")
def impact(event_id: str, lead_h: int | None = None, user: dict = Depends(OFFICIAL)):
    e = _event_or_404(event_id)
    q = _p().point_at(e, lead_h)
    if q is None:
        raise HTTPException(404, "Event not active at that time")
    pop = q["impact"]["population"] if "wards" in q["impact"]["population"] else imp.population_by_ring(q["zone"])
    assets = q["impact"].get("assets") or imp.assets_in_zone(q["zone"], _p().assets)
    return {"event_id": e["id"], "lead_h": q["lead_h"], "valid_local": q["valid_local"], "zone": q["zone"],
            "population": pop, "assets": assets, "counts": {**q["impact"]["counts"]},
            "vehicles": e.get("vehicles", {}).get("toward", []) if q is e["peak"] else []}


# ------------------------------------------------------------------ maps
def _zone_features(e, q):
    feats = []
    for ring in ("low", "moderate", "high"):
        feats.append({"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [q["zone"]["rings"][ring]]},
                      "properties": {"event_id": e["id"], "ring": ring, "severity": q["severity"], "type": e["type"],
                                     "place": e["place"], "valid_local": q["valid_local"], "lead_h": q["lead_h"]}})
    feats.append({"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [q["footprint"]]},
                  "properties": {"event_id": e["id"], "ring": "footprint", "severity": q["severity"], "type": e["type"]}})
    feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": q["zone"]["center"]},
                  "properties": {"event_id": e["id"], "ring": "center", "severity": q["severity"], "type": e["type"],
                                 "place": e["place"], "people": q["impact"]["population"]["total"]}})
    return feats


@router.get("/maps/risk-zones")
def risk_zones(lead_h: int | None = None, user: dict = Depends(current_user)):
    p = _p()
    feats = []
    for e in p.events():
        q = p.point_at(e, lead_h) if lead_h is not None else e["peak"]
        if q is None or not _active_at(e, lead_h):
            continue
        feats += _zone_features(e, q)
    return {"type": "FeatureCollection", "lead_h": lead_h, "features": feats}


@router.get("/maps/tracks")
def tracks(user: dict = Depends(current_user)):
    feats = []
    for e in _p().events():
        feats.append({"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[q["lon"], q["lat"]] for q in e["track"]]},
                      "properties": {"event_id": e["id"], "kind": "track", "severity": e["severity"]}})
        if e["predicted"]:
            line = [[e["track"][-1]["lon"], e["track"][-1]["lat"]]] + [[q["lon"], q["lat"]] for q in e["predicted"]]
            feats.append({"type": "Feature", "geometry": {"type": "LineString", "coordinates": line},
                          "properties": {"event_id": e["id"], "kind": "predicted", "severity": e["severity"]}})
            # uncertainty cone
            left, right = [], []
            pts = [{"lat": e["track"][-1]["lat"], "lon": e["track"][-1]["lon"], "uncertainty_km": e["track"][-1]["uncertainty_km"] or 10}] + e["predicted"]
            for a, b in zip(pts[:-1], pts[1:]):
                brg = float(bearing_deg(a["lat"], a["lon"], b["lat"], b["lon"]))
                for side, arr in ((90, right), (-90, left)):
                    arr.append(destination(b["lat"], b["lon"], (brg + side) % 360, b["uncertainty_km"]))
            ring = [[pts[0]["lon"], pts[0]["lat"]]] + [[lo, la] for la, lo in right] + [[lo, la] for la, lo in reversed(left)] + [[pts[0]["lon"], pts[0]["lat"]]]
            feats.append({"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring]},
                          "properties": {"event_id": e["id"], "kind": "cone", "severity": e["severity"]}})
        for q in e["track"]:
            feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [q["lon"], q["lat"]]},
                          "properties": {"event_id": e["id"], "kind": "position", "lead_h": q["lead_h"], "severity": q["severity"]}})
    return {"type": "FeatureCollection", "features": feats}


@router.get("/maps/assets")
def assets_geojson(kind: str | None = None, event_id: str | None = None, user: dict = Depends(current_user)):
    p = _p()
    items = p.assets
    ring_of = {}
    if event_id:
        items = _event_or_404(event_id)["peak"]["impact"].get("assets", [])
        ring_of = {a["id"]: a["ring"] for a in items}
    if kind:
        items = [a for a in items if a["kind"] == kind]
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [a["lon"], a["lat"]]},
         "properties": {**{k: a[k] for k in ("id", "kind", "name", "city", "capacity")}, "ring": ring_of.get(a["id"], a.get("ring"))}}
        for a in items]}


@router.get("/maps/wards")
def wards(user: dict = Depends(current_user)):
    return get_population().wards_geojson()


@router.get("/maps/vehicles")
def vehicles_geojson(event_id: str | None = None, user: dict = Depends(current_user)):
    feats = []
    for e in _p().events():
        if event_id and e["id"] != event_id:
            continue
        toward = {v["id"]: v for v in e.get("vehicles", {}).get("toward", [])}
        for v in e.get("vehicles", {}).get("all", []):
            t = toward.get(v["id"])
            feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [v["lon"], v["lat"]]},
                          "properties": {**v, "event_id": e["id"], "status": t["status"] if t else "clear",
                                         "eta_min": t["eta_min"] if t else None, "ring": t["ring"] if t else None}})
    return {"type": "FeatureCollection", "features": feats}


# ------------------------------------------------------------------ population
@router.get("/population/districts")
def districts(state: str | None = None, q: str | None = None, limit: int = 50, user: dict = Depends(OFFICIAL)):
    return get_population().district_table(state=state, q=q, limit=limit)


@router.get("/population/at")
def population_at(lat: float, lon: float, radius_km: float = 3.0, user: dict = Depends(OFFICIAL)):
    from app.geo import ellipse_polygon
    return get_population().in_polygon(ellipse_polygon(lat, lon, radius_km, radius_km))


# ------------------------------------------------------------------ vehicles
@router.get("/vehicles")
def vehicles(user: dict = Depends(OFFICIAL)):
    out = []
    for e in _p().events():
        for v in e.get("vehicles", {}).get("toward", []):
            out.append({**v, "event_id": e["id"], "event_place": e["place"], "event_severity": e["severity"],
                        "valid_local": e["peak"]["valid_local"]})
    return {"tracked": sum(e.get("vehicles", {}).get("tracked", 0) for e in _p().events()),
            "toward": sorted(out, key=lambda v: (v["eta_min"], -SEV_RANK[v["event_severity"]])),
            "rule": "Flagged when inside a ring, or heading within 30° of the zone and projected to enter it within 60 min at current speed.",
            "data_source": "simulated"}


def _routes_for(v, zone):
    """Straight 60-minute projection vs a detour skirting the outer ring."""
    speed = v["speed_kmh"]
    direct = [[v["lon"], v["lat"]]]
    for m in range(5, 61, 5):
        la, lo = destination(v["lat"], v["lon"], v["heading_deg"], speed * m / 60)
        direct.append([round(lo, 5), round(la, 5)])
    clat, clon = zone["center"][1], zone["center"][0]
    r_low = zone["radii_km"]["low"] * 1.5          # outer ring incl. its along-track stretch
    d_in = float(haversine_km(v["lat"], v["lon"], clat, clon))
    r = max(min(r_low + 3, d_in * 0.97), r_low * 1.1)
    end_lat, end_lon = direct[-1][1], direct[-1][0]
    if float(haversine_km(end_lat, end_lon, clat, clon)) < r:  # journey ends inside: continue past the zone
        end_lat, end_lon = destination(clat, clon, float(bearing_deg(v["lat"], v["lon"], clat, clon)), r * 1.4)
    b_in = float(bearing_deg(clat, clon, v["lat"], v["lon"]))
    b_out = float(bearing_deg(clat, clon, end_lat, end_lon))
    side = 1 if ((v["detour_heading_deg"] - v["heading_deg"] + 360) % 360) < 180 else -1
    sweep = (b_out - b_in) % 360 if side > 0 else -((b_in - b_out) % 360)
    if abs(sweep) > 250:                             # take the shorter way round
        sweep = sweep - 360 if sweep > 0 else sweep + 360
    safer = [[v["lon"], v["lat"]]]
    steps = 14
    for k in range(steps + 1):
        la, lo = destination(clat, clon, (b_in + sweep * k / steps) % 360, r)
        safer.append([round(lo, 5), round(la, 5)])
    safer.append([round(end_lon, 5), round(end_lat, 5)])
    direct[-1] = [round(end_lon, 5), round(end_lat, 5)]

    def length(line):
        return sum(float(haversine_km(a[1], a[0], b[1], b[0])) for a, b in zip(line[:-1], line[1:]))
    extra = max(1, round((length(safer) - length(direct)) / max(speed, 5) * 60))
    return direct, safer, extra


@router.get("/traveller/status")
def traveller_status(vehicle_id: str | None = None, user: dict = Depends(current_user)):
    p = _p()
    cand = []
    for e in p.events():
        for v in e.get("vehicles", {}).get("toward", []):
            cand.append((e, v))
    if user["role"] == "traveller" and user.get("vehicle_id"):
        vehicle_id = user["vehicle_id"]
        if not any(c[1]["id"] == vehicle_id for c in cand):   # this bus is not heading into any zone
            v = next((x for e in p.events() for x in e.get("vehicles", {}).get("all", []) if x["id"] == vehicle_id), None)
            near = None
            if v:
                e = min(p.events(), key=lambda e: float(haversine_km(v["lat"], v["lon"], e["peak"]["lat"], e["peak"]["lon"])))
                near = {"event": _lite(e), "distance_km": round(float(haversine_km(v["lat"], v["lon"], e["peak"]["lat"], e["peak"]["lon"])), 1)}
            return {"clear": True, "vehicle": v, "nearest": near}
    if not cand:
        return {"clear": True, "vehicle": None, "nearest": None}
    if vehicle_id:
        match = [c for c in cand if c[1]["id"] == vehicle_id]
        if not match:
            raise HTTPException(404, "Vehicle is not heading into any risk zone")
        e, v = match[0]
    else:  # demo: a bus heading into the most populated high-impact zone
        cand.sort(key=lambda c: (c[0]["location"]["nearest_city"] != "Bengaluru", c[1]["status"] != "approaching",
                                 c[1]["kind"] != "bus", -c[0]["peak"]["impact"]["population"]["total"], -c[1]["eta_min"]))
        e, v = cand[0]
    zone = e["peak"]["zone"]
    direct, safer, extra = _routes_for(v, zone)
    alert = next((a for a in p.store.alerts(event_id=e["id"], role="traveller")), None)
    return {
        "vehicle": v, "event": _lite(e), "zone": zone,
        "routes": {"current": direct, "safer": safer, "extra_min": extra},
        "alert": alert, "guidance": composer.GUIDANCE.get(e["type"], {}).get("traveller", []),
        "valid_local": e["peak"]["valid_local"],
    }


# ------------------------------------------------------------------ institutions
def _asset_exposure(p, asset):
    hits = []
    for e in p.events():
        for q in e["track"]:
            ring = imp.ring_of(asset["lat"], asset["lon"], q["zone"])
            if ring:
                hits.append((e, q, ring))
    return hits


@router.get("/institutions")
def institutions(kind: str | None = None, at_risk: bool = True, user: dict = Depends(require("official", "institution"))):
    p = _p()
    out = []
    for e in p.events():
        for a in e["peak"]["impact"].get("assets", []):
            if kind and a["kind"] != kind:
                continue
            ack = p.store.acknowledgements(a["id"])
            out.append({**a, "event_id": e["id"], "event_severity": e["severity"], "event_type": e["type"],
                        "valid_local": e["peak"]["valid_local"], "acknowledged": bool(ack)})
    if not at_risk:
        seen = {o["id"] for o in out}
        out += [{**a, "ring": None} for a in p.assets if a["id"] not in seen and (not kind or a["kind"] == kind)]
    return out


@router.get("/institutions/me")
def my_institution(user: dict = Depends(require("institution", "official"))):
    p = _p()
    if user.get("asset_id"):
        return {"asset_id": user["asset_id"]}
    kind = user.get("asset_kind", "school")
    order = {"high": 0, "moderate": 1, "low": 2}
    best = None
    for e in p.events():
        for a in e["peak"]["impact"].get("assets", []):
            if a["kind"] != kind:
                continue
            key = (order[a["ring"]], -SEV_RANK[e["severity"]], a["distance_km"])
            if best is None or key < best[0]:
                best = (key, a)
    if not best:
        return {"asset_id": next(a["id"] for a in p.assets if a["kind"] == kind)}
    return {"asset_id": best[1]["id"]}


def _own(user, asset_id):
    if user["role"] == "institution" and user.get("asset_id") and user["asset_id"] != asset_id:
        raise HTTPException(403, "You can only see your own institution")


CHECKLISTS = {
    "school": ["Share the alert with all staff", "Confirm parent contact list is current", "Decide dismissal / closure time",
               "Clear drains and move records off the ground floor", "Check school bus routes avoid risk zones",
               "Name a staff lead for shelter coordination"],
    "hospital": ["Test backup power and fuel", "Move critical stock above ground level", "Review surge bed capacity",
                 "Confirm ambulance routes avoid risk zones", "Brief emergency department staff"],
    "rescue_team": ["Confirm personnel and equipment", "Pre-position at staging point", "Check communication links"],
}


@router.get("/institutions/{asset_id}/status")
def institution_status(asset_id: str, user: dict = Depends(require("institution", "official"))):
    _own(user, asset_id)
    p = _p()
    a = p.asset_by_id.get(asset_id)
    if not a:
        raise HTTPException(404, "Unknown institution")
    hits = _asset_exposure(p, a)
    order = {"high": 0, "moderate": 1, "low": 2}
    exposure = None
    if hits:
        e, q, ring = min(hits, key=lambda h: (order[h[2]], -SEV_RANK[h[1]["severity"]], h[1]["lead_h"]))
        first = min(h[1]["lead_h"] for h in hits if h[0]["id"] == e["id"])
        last = max(h[1]["lead_h"] for h in hits if h[0]["id"] == e["id"])
        wx = p.weather_series(a["lat"], a["lon"])
        role = "school" if a["kind"] == "school" else "hospital" if a["kind"] == "hospital" else "rescue"
        alerts = [x for x in p.store.alerts(event_id=e["id"]) if x["role"] == role]
        exposure = {
            "event": _lite(e), "ring": ring, "worst_valid_local": q["valid_local"], "worst_lead_h": q["lead_h"],
            "first_lead_h": first, "last_lead_h": last,
            "distance_km": round(float(haversine_km(a["lat"], a["lon"], q["zone"]["center"][1], q["zone"]["center"][0])), 2),
            "zone": q["zone"], "weather": wx, "alerts": alerts,
            "guidance": composer.GUIDANCE.get(e["type"], {}).get(role, []),
            "confidence": q["probability"],
        }
    done = p.store.checklist(asset_id)
    items = CHECKLISTS.get(a["kind"], CHECKLISTS["school"])
    return {"asset": a, "exposure": exposure, "issue_time": p.state["run"]["issue_time"],
            "checklist": [{"item": i, "done": done.get(i, False)} for i in items],
            "acknowledgements": p.store.acknowledgements(asset_id)}


class AckBody(BaseModel):
    alert_id: str | None = None
    note: str = ""


@router.post("/institutions/{asset_id}/acknowledge")
def acknowledge(asset_id: str, body: AckBody, user: dict = Depends(require("institution", "official"))):
    _own(user, asset_id)
    p = _p()
    p.store.acknowledge(body.alert_id or "", asset_id, user["id"], body.note)
    p.store.audit(user["id"], "acknowledge", {"asset_id": asset_id, "alert_id": body.alert_id})
    return {"ok": True, "acknowledgements": p.store.acknowledgements(asset_id)}


class CheckBody(BaseModel):
    item: str
    done: bool


@router.post("/institutions/{asset_id}/checklist")
def checklist(asset_id: str, body: CheckBody, user: dict = Depends(require("institution", "official"))):
    _own(user, asset_id)
    _p().store.set_checklist(asset_id, body.item, body.done)
    return {"ok": True}


# ------------------------------------------------------------------ citizens
@router.get("/citizen/status")
def citizen_status(lat: float | None = None, lon: float | None = None, user: dict = Depends(current_user)):
    p = _p()
    home = None
    if (lat is None or lon is None) and user.get("home_lat") is not None:   # registered citizen: their home area
        lat, lon, home = user["home_lat"], user["home_lon"], user.get("home_label")
    if lat is None or lon is None:  # demo: a point in the high ring of the most-populated event
        e = max(p.events(), key=lambda e: (e["location"]["nearest_city"] == "Bengaluru" and e["location"]["city_distance_km"] < 30,
                                           e["peak"]["impact"]["population"]["total"]))
        la, lo = destination(e["peak"]["lat"], e["peak"]["lon"], 200, 1.6)
        lat, lon = round(la, 5), round(lo, 5)
    order = {"high": 0, "moderate": 1, "low": 2}
    hits = []
    for e in p.events():
        for q in e["track"]:
            ring = imp.ring_of(lat, lon, q["zone"])
            if ring:
                hits.append((e, q, ring))
    wx = p.weather_series(lat, lon)
    ward = None
    pop = get_population()
    wi = pop._ward_index(np.array([lat]), np.array([lon]))[0]
    if wi >= 0:
        w = pop.wards[wi]
        ward = {"ward_no": w["ward_no"], "ward_name": w["ward_name"]}
    shelters = sorted((a for a in p.assets if a["kind"] == "school"),
                      key=lambda a: float(haversine_km(lat, lon, a["lat"], a["lon"])))
    res = {"lat": lat, "lon": lon, "home_label": home, "ward": ward, "weather": wx, "risk": None,
           "helplines": [{"name": "Disaster helpline", "number": "1070"}, {"name": "Emergency", "number": "112"}]}
    if hits:
        e, q, ring = min(hits, key=lambda h: (order[h[2]], h[1]["lead_h"]))
        # nearest shelter outside the worst zone
        shelter = next((s for s in shelters if not imp.ring_of(s["lat"], s["lon"], q["zone"])), shelters[0] if shelters else None)
        res["risk"] = {
            "event": _lite(e), "ring": ring, "valid_local": q["valid_local"], "lead_h": q["lead_h"], "zone": q["zone"],
            "distance_km": round(float(haversine_km(lat, lon, q["zone"]["center"][1], q["zone"]["center"][0])), 2),
            "guidance": composer.GUIDANCE.get(e["type"], {}).get("citizen", []),
            "alert": next((x for x in p.store.alerts(event_id=e["id"], role="citizen")), None),
        }
        if shelter:
            res["shelter"] = {**shelter, "distance_km": round(float(haversine_km(lat, lon, shelter["lat"], shelter["lon"])), 2),
                              "note": "Demo: nearest school outside the risk zone; real shelters come from the SDMA list."}
    return res


# ------------------------------------------------------------------ rescue
@router.get("/rescue/orders")
def rescue_orders(unit_id: str | None = None, user: dict = Depends(require("rescue", "official"))):
    if user["role"] == "rescue":
        unit_id = user.get("asset_id")
    orders = _p().store.orders(unit_id)
    return sorted(orders, key=lambda o: (o["status"] != "issued", o["window"]["start"]))


class OrderStatus(BaseModel):
    status: str
    note: str = ""


@router.post("/rescue/orders/{order_id}/status")
def order_status(order_id: str, body: OrderStatus, user: dict = Depends(require("rescue", "official"))):
    if body.status not in ("issued", "accepted", "en_route", "on_site", "constraint", "completed"):
        raise HTTPException(400, "Invalid status")
    if user["role"] == "rescue" and not any(o["order_id"] == order_id for o in _p().store.orders(user.get("asset_id"))):
        raise HTTPException(403, "This order belongs to another unit")
    o = _p().store.set_order_status(order_id, body.status, body.note)
    if not o:
        raise HTTPException(404, "Unknown order")
    _p().store.audit(user["id"], "order_status", {"order_id": order_id, "status": body.status})
    return o


# ------------------------------------------------------------------ alerts
@router.get("/alerts")
def alerts(status: str | None = None, role: str | None = None, event_id: str | None = None, user: dict = Depends(OFFICIAL)):
    p = _p()
    return p.store.alerts(run_id=p.state["run"]["run_id"], status=status, role=role, event_id=event_id)


@router.get("/alerts/feed")
def alerts_feed(user: dict = Depends(current_user)):
    """Sent alerts visible to the signed-in role (in-app channel)."""
    p = _p()
    role_map = {"institution": ("school", "hospital"), "rescue": ("rescue",), "citizen": ("citizen",),
                "traveller": ("traveller",), "official": ("official",)}
    roles = role_map.get(user["role"], ())
    return [a for a in p.store.alerts(run_id=p.state["run"]["run_id"], status="sent") if a["role"] in roles]


class DraftBody(BaseModel):
    event_id: str
    role: str
    language: str = "en"


@router.post("/alerts/draft")
def alert_draft(body: DraftBody, user: dict = Depends(OFFICIAL)):
    if body.role not in ("official", "school", "hospital", "rescue", "citizen", "traveller"):
        raise HTTPException(400, "Unknown role")
    return _p().draft_alert(_event_or_404(body.event_id), body.role, body.language, created_by=user["id"])


class EditBody(BaseModel):
    title: str | None = None
    message: str | None = None


@router.patch("/alerts/{alert_id}")
def alert_edit(alert_id: str, body: EditBody, user: dict = Depends(OFFICIAL)):
    p = _p()
    a = p.store.alert(alert_id)
    if not a:
        raise HTTPException(404, "Unknown alert")
    if a["approval_status"] != "draft":
        raise HTTPException(409, "Only drafts can be edited")
    if body.title:
        a["title"] = body.title
    if body.message:
        a["message"] = body.message
    a["generated_by"] = f"{a['generated_by']}+edited"
    p.store.save_alert(a)
    return a


@router.post("/alerts/{alert_id}/approve")
def alert_approve(alert_id: str, user: dict = Depends(OFFICIAL)):
    a = _p().approve_alert(alert_id, user["name"])
    if not a:
        raise HTTPException(404, "Unknown alert")
    return {"alert": a, "deliveries": _p().store.deliveries(alert_id)}


class RejectBody(BaseModel):
    reason: str = ""


@router.post("/alerts/{alert_id}/reject")
def alert_reject(alert_id: str, body: RejectBody, user: dict = Depends(OFFICIAL)):
    a = _p().reject_alert(alert_id, user["name"], body.reason)
    if not a:
        raise HTTPException(404, "Unknown alert")
    return a


@router.get("/alerts/{alert_id}/deliveries")
def alert_deliveries(alert_id: str, user: dict = Depends(OFFICIAL)):
    return _p().store.deliveries(alert_id)


# ------------------------------------------------------------------ copilot
class AskBody(BaseModel):
    question: str
    history: list = []


@router.post("/copilot/ask")
def copilot_ask(body: AskBody, user: dict = Depends(OFFICIAL)):
    p = _p()
    res = Copilot(p).ask(body.question[:2000], body.history)
    p.store.audit(user["id"], "copilot", {"q": body.question, "tools": [c["name"] for c in res["tool_calls"]], "mode": res["mode"]})
    return res


# ------------------------------------------------------------------ reports & analytics
@router.get("/reports")
def reports(user: dict = Depends(OFFICIAL)):
    p = _p()
    return {"runs": p.store.runs(), "events": p.store.event_history(), "audit": p.store.audit_log(50)}


@router.get("/reports/events.csv", response_class=PlainTextResponse)
def report_csv(user: dict = Depends(OFFICIAL)):
    return PlainTextResponse(events_csv(_p().events()), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=weatherpulse_events.csv"})


@router.get("/reports/situation.pdf")
def report_run_pdf(user: dict = Depends(OFFICIAL)):
    p = _p()
    pdf = run_pdf(p.state["run"], p.events(), p.store.alerts(run_id=p.state["run"]["run_id"]))
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=weatherpulse_situation_report.pdf"})


@router.get("/reports/{event_id}.pdf")
def report_event_pdf(event_id: str, user: dict = Depends(current_user)):
    p = _p()
    pdf = event_pdf(_event_or_404(event_id), p.state["run"])
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={event_id}.pdf"})


@router.get("/analytics")
def analytics(user: dict = Depends(OFFICIAL)):
    p = _p()
    evs = p.events()
    run = p.state["run"]
    alerts = p.store.alerts(run_id=run["run_id"])
    dels = p.store.deliveries()
    by_day = {}
    for e in evs:
        d = e["window"]["start_lead_h"] // 24
        by_day[d] = by_day.get(d, 0) + 1
    return {
        "by_type": {t: sum(1 for e in evs if e["type"] == t) for t in {e["type"] for e in evs}},
        "by_severity": {s: sum(1 for e in evs if e["severity"] == s) for s in ("High", "Moderate", "Low")},
        "by_lead_day": [{"day": d, "events": by_day.get(d, 0)} for d in range(0, settings.max_lead_hours // 24 + 1)],
        "people_by_event": [{"event_id": e["id"], "place": e["place"], **{k: e["peak"]["impact"]["population"][k] for k in ("high", "moderate", "low", "total")}} for e in evs],
        "alerts": {"total": len(alerts), "by_status": {s: sum(1 for a in alerts if a["approval_status"] == s) for s in ("draft", "sent", "rejected")},
                   "by_role": {r: sum(1 for a in alerts if a["role"] == r) for r in {a["role"] for a in alerts}}},
        "deliveries": {s: sum(1 for d in dels if d["delivery_status"] == s) for s in {d["delivery_status"] for d in dels}},
        "model": {k: v for k, v in p.models.metrics.items() if k != "type_report"},
        "model_report": p.models.metrics.get("type_report", {}),
        "trained_at": p.models.trained_at,
        "pipeline": {"objects": run["n_objects"], "tracks": run["n_tracks"], "runtime_s": run["runtime_s"], "qc": run["qc"]},
    }


@router.get("/settings/status")
def settings_status(user: dict = Depends(OFFICIAL)):
    p = _p()
    pop = get_population()
    return {
        "data_sources": [
            {"name": "Forecast", "value": p.state["run"]["provider"], "mode": "synthetic", "note": "Swap for NCUM/NEPS via app/data/loaders.py"},
            {"name": "Baseline climatology", "value": "ERA5-like synthetic climatology", "mode": "synthetic", "note": "load_reanalysis_climatology() reads ERA5/IMDAA NetCDF"},
            {"name": "Population", "value": f"Census of India 2011 · {len(pop.wards)} BBMP wards + {len(pop.districts)} districts", "mode": "official",
             "note": f"Projected ×{PROJECTION_FACTOR}; exact district polygons: {'yes' if pop.dpolys else 'no (run scripts/prepare_reference_data.py)'}"},
            {"name": "Institutions", "value": f"{len(p.assets)} synthetic schools, hospitals, rescue units", "mode": "synthetic", "note": "load_osm_assets() reads an OSM GeoJSON export"},
            {"name": "Vehicles", "value": "Simulated GPS feed", "mode": "synthetic", "note": "Authorised fleet feeds later"},
            {"name": "Base map", "value": "OpenFreeMap / OpenStreetMap", "mode": "public", "note": "No key needed"},
        ],
        "thresholds": {"z_threshold": settings.z_threshold, "min_object_cells": settings.min_object_cells,
                       "ring_radii_km": settings.ring_radii_km, "vehicle_rule": "30° heading, 60 min horizon"},
        "model": {"version": p.state["run"]["model_version"], "trained_at": p.models.trained_at,
                  "metrics": {k: v for k, v in p.models.metrics.items() if k != "type_report"}},
        "integrations": {"gemini": gemini.enabled(), "gemini_model": settings.gemini_model if gemini.enabled() else None,
                         "gemini_status": gemini.status(), "gemini_in_pipeline": settings.gemini_in_pipeline,
                         "sms": settings.sms_provider, "email": settings.email_provider},
        "users": _user_summary(),
    }


def _user_summary():
    from app.accounts import get_accounts
    a = get_accounts()
    return [{"role": r, "label": l, "count": a.count(role=r)} for r, l in
            (("official", "Government officials"), ("institution", "Schools, colleges & hospitals"), ("rescue", "Rescue units"),
             ("traveller", "Bus drivers"), ("citizen", "Citizens (registered + samples)"))]


# ------------------------------------------------------------------ pipeline & learning
class RunBody(BaseModel):
    seed: int | None = None


@router.post("/pipeline/run")
def pipeline_run(body: RunBody, user: dict = Depends(OFFICIAL)):
    run = get_pipeline().run(seed=body.seed)
    return {k: run[k] for k in ("run_id", "issue_time_local", "summary", "runtime_s")}


class FeedbackBody(BaseModel):
    event_id: str
    observed: bool
    observed_type: str | None = None
    observed_severity: str | None = None
    notes: str = ""


@router.post("/feedback")
def feedback(body: FeedbackBody, user: dict = Depends(OFFICIAL)):
    p = _p()
    e = _event_or_404(body.event_id)
    from app.pipeline.detection import FEATURE_NAMES
    pk = e["peak"]
    feats = [pk["z"]["precip"], pk["z"]["t2m"], pk["z"]["wind"], pk["z"]["mslp"]]
    p.store.add_feedback({**body.model_dump(), "run_id": p.state["run"]["run_id"], "features": feats})
    p.store.audit(user["id"], "feedback", body.model_dump())
    return {"ok": True, "stored": len(p.store.feedback()), "note": "Used at the next retraining", "feature_names": FEATURE_NAMES[:4]}


_retrain_state = {"running": False, "last": None}


@router.post("/models/retrain")
def retrain(user: dict = Depends(OFFICIAL)):
    if _retrain_state["running"]:
        return {"status": "already running"}

    def job():
        from app.pipeline.models import ModelBundle, train_all
        _retrain_state["running"] = True
        try:
            mb = train_all(n_scenarios=24, verbose=False)
            mb.save()
            get_pipeline().models = ModelBundle.load()
            _retrain_state["last"] = mb.metrics
        finally:
            _retrain_state["running"] = False

    threading.Thread(target=job, daemon=True).start()
    return {"status": "started"}


@router.get("/models/retrain")
def retrain_status(user: dict = Depends(OFFICIAL)):
    last = _retrain_state["last"]
    return {"running": _retrain_state["running"], "last": {k: v for k, v in (last or {}).items() if k != "type_report"} or None}
