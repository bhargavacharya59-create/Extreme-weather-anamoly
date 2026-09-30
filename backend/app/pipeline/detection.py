"""Step 3 - AI analysis & detection.

1. Statistical trigger: cells whose ensemble-mean standardised anomaly exceeds
   the threshold in the "extreme" direction of any variable.
2. Connected-component labelling turns triggered cells into anomaly objects.
3. Per object we compute a feature vector (peak / mean anomalies, area, ensemble
   exceedance probability, ensemble position spread, location, season, lead).
4. ML models (app/pipeline/models.py) classify event type (or 'noise'),
   severity (High / Moderate / Low) and an unsupervised anomaly score.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from scipy.ndimage import label

from app.config import settings
from app.data.synthetic import VARIABLES, ForecastBundle, Grid
from app.geo import haversine_km
from app.pipeline.preprocess import Preprocessed

# sign of the "extreme" direction checked per variable
TRIGGERS = [("precip", +1), ("t2m", +1), ("t2m", -1), ("wind", +1), ("mslp", -1)]

FEATURE_NAMES = [
    "zp_precip", "zp_t2m", "zp_wind", "zp_mslp",
    "zm_precip", "zm_t2m", "zm_wind", "zm_mslp",
    "log_area_km2", "ens_prob", "spread_km", "lat", "lon",
    "month_sin", "month_cos", "lead_h",
]


def severity_signal(z: dict) -> np.ndarray:
    """Per-cell extremeness: the largest anomaly in any extreme direction."""
    return np.maximum.reduce([
        z["precip"], z["t2m"], -z["t2m"], z["wind"], -z["mslp"],
    ])


@dataclass
class AnomalyObject:
    step: int
    lead_h: int
    lat: float                 # severity-weighted centroid
    lon: float
    peak_lat: float
    peak_lon: float
    area_km2: float
    n_cells: int
    features: dict
    values: dict               # physical ensemble-mean values at peak
    z_peak: dict
    ens_prob: float
    spread_km: float
    footprint: list = field(default_factory=list)   # [[lon, lat], ...] convex hull
    member_centroids: list = field(default_factory=list)
    # filled by the models
    type: str = "unknown"
    type_proba: dict = field(default_factory=dict)
    severity: str = "Low"
    severity_score: float = 0.0
    anomaly_score: float = 0.0

    def feature_vector(self) -> list[float]:
        return [float(self.features[k]) for k in FEATURE_NAMES]


def _hull(lons: np.ndarray, lats: np.ndarray, res: float) -> list:
    pts = np.column_stack([lons, lats])
    # expand each cell to its corners so single-row objects still form a polygon
    h = res / 2
    corners = np.concatenate([pts + [dx, dy] for dx in (-h, h) for dy in (-h, h)])
    try:
        from scipy.spatial import ConvexHull

        hull = ConvexHull(corners)
        ring = corners[hull.vertices]
    except Exception:  # degenerate
        ring = corners[:4]
    ring = [[round(float(x), 4), round(float(y), 4)] for x, y in ring]
    ring.append(ring[0])
    return ring


def detect(bundle: ForecastBundle, pre: Preprocessed, thr: float | None = None) -> list[AnomalyObject]:
    thr = settings.z_threshold if thr is None else thr
    grid: Grid = bundle.grid
    s_mean = severity_signal(pre.z_mean)                  # (T, ny, nx)
    s_mem = severity_signal(pre.z)                        # (M, T, ny, nx)
    phys_mean = {v: np.nanmean(bundle.fields[v], axis=0) for v in VARIABLES}
    month = bundle.month
    objects: list[AnomalyObject] = []
    structure = np.ones((3, 3), dtype=int)

    for ti, lead in enumerate(bundle.lead_hours):
        mask = s_mean[ti] > thr
        if not mask.any():
            continue
        lab, n = label(mask, structure=structure)
        for k in range(1, n + 1):
            cells = lab == k
            n_cells = int(cells.sum())
            if n_cells < settings.min_object_cells:
                continue
            iy, ix = np.nonzero(cells)
            w = (s_mean[ti][cells] - thr + 1e-3) ** 2   # emphasise the core
            lat_c = float(np.average(grid.LAT[cells], weights=w))
            lon_c = float(np.average(grid.LON[cells], weights=w))
            pk = int(np.argmax(s_mean[ti][cells]))
            py, px = iy[pk], ix[pk]
            z_peak = {v: float(pre.z_mean[v][ti, py, px]) for v in VARIABLES}
            z_obj = {v: float(pre.z_mean[v][ti][cells].mean()) for v in VARIABLES}
            area = float(grid.cell_km2[cells].sum())

            # ensemble: exceedance probability + member centroid spread
            y0, y1 = max(iy.min() - 6, 0), min(iy.max() + 7, grid.shape[0])
            x0, x1 = max(ix.min() - 6, 0), min(ix.max() + 7, grid.shape[1])
            member_cent = []
            for m in range(s_mem.shape[0]):
                sm = s_mem[m, ti, y0:y1, x0:x1]
                ex = np.clip(sm - thr, 0, None)
                if ex.sum() > 0:
                    member_cent.append((
                        float(np.average(grid.LAT[y0:y1, x0:x1], weights=ex)),
                        float(np.average(grid.LON[y0:y1, x0:x1], weights=ex)),
                    ))
            ens_prob = float((s_mem[:, ti][:, cells] > thr).mean(axis=0).max())
            if member_cent:
                mc = np.array(member_cent)
                spread = float(np.sqrt(np.mean(haversine_km(mc[:, 0], mc[:, 1], lat_c, lon_c) ** 2)))
            else:
                spread = 0.0

            feats = {
                **{f"zp_{v}": z_peak[v] for v in VARIABLES},
                **{f"zm_{v}": z_obj[v] for v in VARIABLES},
                "log_area_km2": math.log(area),
                "ens_prob": ens_prob,
                "spread_km": spread,
                "lat": lat_c,
                "lon": lon_c,
                "month_sin": math.sin(2 * math.pi * month / 12),
                "month_cos": math.cos(2 * math.pi * month / 12),
                "lead_h": float(lead),
            }
            objects.append(AnomalyObject(
                step=ti, lead_h=int(lead), lat=lat_c, lon=lon_c,
                peak_lat=float(grid.LAT[py, px]), peak_lon=float(grid.LON[py, px]),
                area_km2=area, n_cells=n_cells, features=feats,
                values={v: round(float(phys_mean[v][ti, py, px]), 2) for v in VARIABLES},
                z_peak={v: round(z_peak[v], 2) for v in VARIABLES},
                ens_prob=ens_prob, spread_km=spread,
                footprint=_hull(grid.LON[cells], grid.LAT[cells], grid.res),
                member_centroids=[[round(b, 4), round(a, 4)] for a, b in member_cent],
            ))
    return objects


def rule_based_type(o: AnomalyObject) -> str:
    """Physically-motivated fallback labeller (used if no model is trained)."""
    z = o.z_peak
    if z["wind"] > 2.5 and z["mslp"] < -2.5:
        return "cyclone"
    if z["t2m"] > 2.5 and z["precip"] < 1.5:
        return "heatwave"
    if z["t2m"] < -2.5:
        return "coldwave"
    if z["precip"] > 2.5:
        return "heavy_rainfall"
    return "noise"


def severity_from_z(o: AnomalyObject) -> tuple[str, float]:
    score = float(max(o.z_peak["precip"], abs(o.z_peak["t2m"]), o.z_peak["wind"], -o.z_peak["mslp"]))
    return ("High" if score >= 5.5 else "Moderate" if score >= 4.0 else "Low"), score
