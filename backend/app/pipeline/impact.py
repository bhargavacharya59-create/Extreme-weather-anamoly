"""Step 5 - Dynamic impact zones & impact analysis (Model 4 of the plan).

For every tracked position we build three nested polygons (high / moderate /
lower risk). Base radii are 3 / 5 / 8 km, adapted by
  * severity   - stronger anomalies get larger zones
  * movement   - zones stretch and shift forward along the direction of travel
  * uncertainty- ensemble position spread widens the outer ring
Then we intersect them with population (Census 2011), institutions and
vehicles.
"""
from __future__ import annotations

import math

import numpy as np

from app.config import settings
from app.data.population import get_population
from app.geo import bearing_deg, destination, ellipse_polygon, haversine_km, points_in_polygon

RINGS = ("high", "moderate", "low")
RING_LABEL = {"high": "High · 0–3 km", "moderate": "Moderate · 3–5 km", "low": "Lower · 5–8 km"}


def zone_geometry(lat, lon, severity_score, speed_kmh, heading_deg, uncertainty_km) -> dict:
    base = settings.ring_radii_km
    s = float(np.clip(0.9 + 0.08 * (severity_score - 4.0), 0.85, 1.4))
    stretch = min(speed_kmh / 60.0, 0.5)
    out = {"center": [round(lon, 5), round(lat, 5)], "radii_km": {}, "rings": {}}
    for name, r in zip(RINGS, base):
        r_eff = r * s
        if name == "low":
            r_eff += min(uncertainty_km / 40.0, 3.0)
        a = r_eff * (1 + stretch)
        out["radii_km"][name] = round(r_eff, 2)
        out["rings"][name] = ellipse_polygon(lat, lon, a, r_eff, heading_deg, offset_km=r_eff * stretch * 0.5)
    out["scale"] = round(s, 2)
    return out


def ring_of(lat, lon, zone) -> str | None:
    for name in RINGS:
        if points_in_polygon(np.array([lon]), np.array([lat]), zone["rings"][name])[0]:
            return name
    return None


def population_by_ring(zone) -> dict:
    pop = get_population()
    res = {name: pop.in_polygon(zone["rings"][name]) for name in RINGS}
    high = res["high"]["total"]
    mod = max(res["moderate"]["total"] - high, 0)
    low = max(res["low"]["total"] - res["moderate"]["total"], 0)
    full = res["low"]
    return {
        "high": high, "moderate": mod, "low": low, "total": full["total"],
        "male": full["male"], "female": full["female"], "households": full["households"],
        "area_km2": full["area_km2"], "sources": full["sources"],
        "wards": full["wards"][:40], "wards_count": len(full["wards"]),
        "districts": full["districts"][:10],
        "projection_factor": full.get("projection_factor"),
        "method": "Census 2011 population (ward level where available, else district density), area-weighted to each ring and projected to the present",
    }


def assets_in_zone(zone, assets: list[dict]) -> list[dict]:
    if not assets:
        return []
    lats = np.array([a["lat"] for a in assets])
    lons = np.array([a["lon"] for a in assets])
    clat, clon = zone["center"][1], zone["center"][0]
    near = haversine_km(lats, lons, clat, clon) < 40
    out = []
    ring_arr = np.full(len(assets), None, dtype=object)
    for name in reversed(RINGS):  # low first, then overwrite with inner rings
        idx = np.nonzero(near)[0]
        if idx.size == 0:
            break
        ins = points_in_polygon(lons[idx], lats[idx], zone["rings"][name])
        ring_arr[idx[ins]] = name
    for i in np.nonzero(ring_arr != None)[0]:  # noqa: E711
        a = assets[int(i)]
        out.append({**a, "ring": ring_arr[i], "distance_km": round(float(haversine_km(a["lat"], a["lon"], clat, clon)), 2)})
    order = {n: k for k, n in enumerate(RINGS)}
    return sorted(out, key=lambda x: (order[x["ring"]], x["distance_km"]))


def vehicles_toward(zone, vehicles: list[dict], horizon_min: int = 60, max_angle: float = 30.0, radius_km: float = 45.0) -> list[dict]:
    """Vehicles inside the zone, or heading at it and projected to enter it within
    `horizon_min` minutes at their current speed."""
    clat, clon = zone["center"][1], zone["center"][0]
    out = []
    for v in vehicles:
        d = float(haversine_km(v["lat"], v["lon"], clat, clon))
        if d > radius_km:
            continue
        cur = ring_of(v["lat"], v["lon"], zone)
        brg = float(bearing_deg(v["lat"], v["lon"], clat, clon))
        diff = abs((v["heading_deg"] - brg + 180) % 360 - 180)
        eta, entry_ring = None, None
        if cur is None and diff <= max_angle:
            for minute in range(2, horizon_min + 1, 2):
                la, lo = destination(v["lat"], v["lon"], v["heading_deg"], v["speed_kmh"] * minute / 60)
                r = ring_of(la, lo, zone)
                if r:
                    eta, entry_ring = minute, r
                    break
        if cur or eta is not None:
            # suggest a detour heading: turn away from the zone by 60-90 degrees
            side = 1 if ((v["heading_deg"] - brg + 360) % 360) < 180 else -1
            out.append({
                **v, "distance_km": round(d, 2), "bearing_to_zone": round(brg, 1),
                "angle_off_deg": round(diff, 1), "status": "inside" if cur else "approaching",
                "ring": cur or entry_ring, "eta_min": 0 if cur else eta,
                "detour_heading_deg": round((v["heading_deg"] + side * 75) % 360, 1),
            })
    order = {"high": 0, "moderate": 1, "low": 2}
    return sorted(out, key=lambda x: (x["eta_min"], order.get(x["ring"], 3)))
