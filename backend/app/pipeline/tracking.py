"""Step 4 - Tracking & forecasting (Model 2 + Model 3 of the plan).

* Associates anomaly objects across consecutive forecast steps with the
  Hungarian algorithm (cost = distance, gated by a maximum plausible speed,
  penalised when the event type changes).
* Estimates speed / heading from centroid displacement (least-squares over the
  last few points).
* Ensemble uncertainty: spread of per-member centroids at each step.
* Extends the track beyond its last detection with the trained trajectory
  model (falls back to constant velocity), with a growing uncertainty cone.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import linear_sum_assignment

from app.geo import bearing_deg, compass, haversine_km, to_local_km
from app.pipeline.detection import AnomalyObject

MAX_SPEED_KMH = 45.0          # synoptic systems rarely move faster
COMPATIBLE = {frozenset({"heavy_rainfall", "cyclone"})}  # a cyclone's rain shield may be labelled rain
SEV_RANK = {"Low": 0, "Moderate": 1, "High": 2}


@dataclass
class Track:
    id: str
    points: list = field(default_factory=list)   # AnomalyObject, ordered by lead
    predicted: list = field(default_factory=list)

    @property
    def last(self) -> AnomalyObject:
        return self.points[-1]

    @property
    def type(self) -> str:
        votes: dict = {}
        for p in self.points:
            votes[p.type] = votes.get(p.type, 0) + max(p.severity_score, 0.1)
        return max(votes, key=votes.get)

    @property
    def peak(self) -> AnomalyObject:
        return max(self.points, key=lambda p: (SEV_RANK[p.severity], p.severity_score))


def associate(objects: list[AnomalyObject], step_hours: int, min_len: int = 3) -> list[Track]:
    by_step: dict[int, list[AnomalyObject]] = {}
    for o in objects:
        if o.type != "noise":
            by_step.setdefault(o.step, []).append(o)
    active: list[Track] = []
    done: list[Track] = []
    counter = 0
    for step in sorted(by_step):
        cur = by_step[step]
        # tracks whose last point is from the previous step (allow one missed step)
        live = [t for t in active if step - t.last.step <= 2]
        done += [t for t in active if step - t.last.step > 2]
        active = live
        if active and cur:
            cost = np.full((len(active), len(cur)), 1e6)
            for i, t in enumerate(active):
                gap_h = (step - t.last.step) * step_hours
                # predict where the track should be now (constant velocity) and gate around it
                if len(t.points) >= 2:
                    _, hdg, vx, vy = motion(t.points)
                    plat = t.last.lat + vy * gap_h / 111.32
                    plon = t.last.lon + vx * gap_h / (111.32 * math.cos(math.radians(t.last.lat)))
                    gate = 25.0 * gap_h + 60.0
                else:
                    plat, plon, gate = t.last.lat, t.last.lon, MAX_SPEED_KMH * gap_h + 40.0
                for j, o in enumerate(cur):
                    if o.type != t.type and frozenset({o.type, t.type}) not in COMPATIBLE:
                        continue
                    d = float(haversine_km(plat, plon, o.lat, o.lon))
                    if d <= gate:
                        cost[i, j] = d + (60.0 if o.type != t.type else 0.0)
            r, c = linear_sum_assignment(cost)
            matched_obj = set()
            for i, j in zip(r, c):
                if cost[i, j] < 1e6:
                    active[i].points.append(cur[j])
                    matched_obj.add(j)
            new = [o for j, o in enumerate(cur) if j not in matched_obj]
        else:
            new = cur
        for o in new:
            counter += 1
            active.append(Track(id=f"T{counter:03d}", points=[o]))
    done += active
    return [t for t in done if len(t.points) >= min_len]


def motion(points: list[AnomalyObject], n: int = 4) -> tuple[float, float, float, float]:
    """Return (speed km/h, heading deg, vx km/h east, vy km/h north)."""
    pts = points[-n:]
    if len(pts) < 2:
        return 0.0, 0.0, 0.0, 0.0
    lat0, lon0 = pts[0].lat, pts[0].lon
    x, y = to_local_km([p.lat for p in pts], [p.lon for p in pts], lat0, lon0)
    t = np.array([p.lead_h for p in pts], dtype=float)
    vx = float(np.polyfit(t, x, 1)[0])
    vy = float(np.polyfit(t, y, 1)[0])
    speed = math.hypot(vx, vy)
    heading = (math.degrees(math.atan2(vx, vy)) + 360) % 360
    return speed, heading, vx, vy


def extend(track: Track, models, step_hours: int, horizon_h: int = 48) -> list[dict]:
    """Predict positions beyond the last detection with the trajectory model."""
    pts = track.points
    if len(pts) < 2:
        return []
    disp = []
    for a, b in zip(pts[:-1], pts[1:]):
        x, y = to_local_km(b.lat, b.lon, a.lat, a.lon)
        scale = step_hours / max(b.lead_h - a.lead_h, 1)
        disp.append((float(x) * scale, float(y) * scale))
    lat, lon = pts[-1].lat, pts[-1].lon
    base_unc = max(pts[-1].spread_km, 10.0)
    out = []
    for k in range(1, horizon_h // step_hours + 1):
        dx, dy = models.predict_next(disp, lat, lon) if models is not None else (
            float(np.mean([d[0] for d in disp[-3:]])), float(np.mean([d[1] for d in disp[-3:]])))
        lat = lat + dy / 111.32
        lon = lon + dx / (111.32 * math.cos(math.radians(lat)))
        disp.append((dx, dy))
        out.append({
            "lead_h": int(pts[-1].lead_h + k * step_hours),
            "lat": round(lat, 4), "lon": round(lon, 4),
            "uncertainty_km": round(base_unc + 12.0 * k, 1),
        })
    return out


def describe(track: Track) -> dict:
    speed, heading, _, _ = motion(track.points)
    return {"speed_kmh": round(speed, 1), "heading_deg": round(heading, 1), "direction": compass(heading) if speed > 1 else "Stationary"}


def bearing_to(track: Track, lat: float, lon: float) -> float:
    return float(bearing_deg(track.last.lat, track.last.lon, lat, lon))
