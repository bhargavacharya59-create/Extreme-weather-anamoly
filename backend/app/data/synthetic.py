"""Synthetic data generators.

Real inputs (NCUM/NEPS ensemble forecasts, ERA5/IMDAA reanalysis, IMD
observations, OpenStreetMap assets, census population) need registrations and
large downloads, so every one of them has a synthetic stand-in with the same
shape and units. The rest of the pipeline cannot tell the difference, and each
synthetic source can be swapped for a real loader in `app/data/loaders.py`.

Generated here:
  * Grid                  - 0.25 deg India domain (same resolution as ERA5)
  * climatology()         - ERA5-like monthly mean / std per grid cell
  * generate_forecast()   - NEPS-like ensemble: members x lead-steps x lat x lon
                            for precip (mm/6h), t2m (degC), wind (m/s), mslp (hPa),
                            with spatially + temporally correlated noise, missing
                            values, and injected moving extreme-weather events
  * EventSpec / scenarios - ground-truth events (for evaluation and ML labels)
  * generate_assets()     - schools/colleges, hospitals, rescue teams (OSM-like)
  * population_density()  - people / km^2 surface (census/WorldPop-like)
  * generate_vehicles()   - moving buses / cars / trucks (GPS-feed-like)
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

import numpy as np
from scipy.ndimage import gaussian_filter

from app.config import settings
from app.data.cities import CITIES, CITY_CODE
from app.geo import destination, haversine_km, to_local_km

VARIABLES = ("precip", "t2m", "wind", "mslp")
UNITS = {"precip": "mm/6h", "t2m": "degC", "wind": "m/s", "mslp": "hPa"}
EVENT_TYPES = ("heavy_rainfall", "heatwave", "cyclone", "coldwave")

# How each event type perturbs each variable, in multiples of its peak z.
EVENT_SIGNATURE = {
    "heavy_rainfall": {"precip": 1.0, "t2m": -0.3, "wind": 0.35, "mslp": -0.25},
    "heatwave": {"precip": -0.2, "t2m": 1.0, "wind": 0.0, "mslp": 0.15},
    "cyclone": {"precip": 0.75, "t2m": -0.25, "wind": 1.0, "mslp": -1.0},
    "coldwave": {"precip": 0.0, "t2m": -1.0, "wind": 0.25, "mslp": 0.35},
}


# --------------------------------------------------------------------------- grid
@dataclass
class Grid:
    lat_min: float = settings.lat_min
    lat_max: float = settings.lat_max
    lon_min: float = settings.lon_min
    lon_max: float = settings.lon_max
    res: float = settings.grid_res

    def __post_init__(self):
        self.lats = np.round(np.arange(self.lat_min, self.lat_max + 1e-9, self.res), 4)
        self.lons = np.round(np.arange(self.lon_min, self.lon_max + 1e-9, self.res), 4)
        self.LON, self.LAT = np.meshgrid(self.lons, self.lats)
        # approximate cell area (km^2)
        self.cell_km2 = (self.res * 111.32) ** 2 * np.cos(np.radians(self.LAT))

    @property
    def shape(self):
        return self.LAT.shape


# -------------------------------------------------------------------- climatology
_T_A = [22, 24, 28, 31.5, 33, 31, 29, 28.5, 28.5, 27, 24.5, 22.5]
_T_B = [-0.7, -0.6, -0.35, 0, 0.25, 0.25, 0.1, 0.05, 0, -0.3, -0.55, -0.65]
_SW_MONSOON = {6: 0.7, 7: 1.0, 8: 1.0, 9: 0.7}
_NE_MONSOON = {10: 0.8, 11: 1.0, 12: 0.6}


def _sig(x):
    return 1.0 / (1.0 + np.exp(-x))


def climatology(grid: Grid, month: int) -> dict:
    """ERA5-like climatological mean and std for each variable.

    Precipitation is strongly skewed, so its statistics are stored in
    cube-root space (key 'precip' holds cbrt(mm/6h) mean/std); see
    `to_model_space` / `to_physical`.
    """
    lat, lon = grid.LAT, grid.LON
    m = month - 1
    winter = 1.0 if month in (11, 12, 1, 2) else 0.0
    sw = _SW_MONSOON.get(month, 0.0)
    ne = _NE_MONSOON.get(month, 0.0)

    # temperature (2 m)
    t = _T_A[m] + _T_B[m] * (lat - 20)
    t -= np.clip(lat - 30, 0, None) * 2.5  # Himalaya
    t -= 3.0 * np.exp(-(((lat - 14.5) / 3.0) ** 2 + ((lon - 76.8) / 2.5) ** 2))  # Deccan plateau
    t_std = 1.4 + 0.08 * np.clip(lat - 15, 0, None) * (1 + 0.5 * winter)

    # precipitation (mm per 6 h)
    ghats = np.exp(-(((lon - 74.2) / 1.2) ** 2)) * ((lat > 8) & (lat < 21))
    northeast = _sig((lon - 89) * 2) * _sig((lat - 22) * 2)
    central = np.exp(-(((lat - 22) / 4) ** 2))
    tn_coast = np.exp(-(((lon - 80) / 1.5) ** 2) - ((lat - 12) / 3) ** 2)
    p_mean = 0.25 + sw * (1.2 + 3.5 * ghats + 3.0 * northeast + 1.0 * central) + ne * 2.0 * tn_coast
    p_mean_c = np.cbrt(p_mean) * 0.85
    p_std_c = 0.35 + 0.25 * np.cbrt(p_mean)

    # 10 m wind speed
    w = 3.5 + 1.5 * sw * (lat < 20) + 1.0 * winter * (lat > 25)
    w_std = np.full_like(w, 2.5)

    # mean sea-level pressure
    heat_low = (1.0 if month in (5, 6) else 0.0) * (lat > 24)
    p = 1012 - 6 * sw * central - 4 * heat_low + 4 * winter * _sig((lat - 22) * 1.5)
    p_std = 2.0 + 0.05 * np.abs(lat - 15)

    return {
        "precip": (p_mean_c.astype(np.float32), p_std_c.astype(np.float32)),
        "t2m": (t.astype(np.float32), t_std.astype(np.float32)),
        "wind": (w.astype(np.float32), w_std.astype(np.float32)),
        "mslp": (p.astype(np.float32), p_std.astype(np.float32)),
    }


def to_model_space(var: str, x: np.ndarray) -> np.ndarray:
    return np.cbrt(np.clip(x, 0, None)) if var == "precip" else x


def to_physical(var: str, x: np.ndarray) -> np.ndarray:
    if var == "precip":
        return np.clip(np.clip(x, 0, None) ** 3, 0, 350.0)
    if var == "wind":
        return np.clip(x, 0, None)
    return x


# ------------------------------------------------------------------------ events
@dataclass
class EventSpec:
    id: str
    type: str
    lat0: float
    lon0: float
    speed_kmh: float
    heading_deg: float
    start_h: float
    duration_h: float
    peak_z: float
    radius_km: float
    name: str = ""

    def position(self, hour: float):
        dist = self.speed_kmh * max(hour - self.start_h, 0.0)
        return destination(self.lat0, self.lon0, self.heading_deg, dist)

    def intensity(self, hour: float) -> float:
        f = (hour - self.start_h) / self.duration_h
        if f < 0 or f > 1:
            return 0.0
        return float(self.peak_z * math.sin(math.pi * f))

    def to_dict(self):
        return asdict(self)


def _aimed(eid, etype, target_lat, target_lon, heading, speed, start_h, duration_h, peak_z, radius, name):
    """Event whose centre passes over (target_lat, target_lon) at peak intensity."""
    peak_h = start_h + duration_h / 2
    lat0, lon0 = destination(target_lat, target_lon, (heading + 180) % 360, speed * (peak_h - start_h))
    return EventSpec(eid, etype, round(lat0, 4), round(lon0, 4), speed, heading, start_h, duration_h, peak_z, radius, name)


def demo_scenario() -> list[EventSpec]:
    """Hand-placed events that peak over populated places (matches the pitch deck:
    a heavy-rain cell over Bengaluru, a Bay-of-Bengal cyclone landfall, etc.)."""
    return [
        _aimed("EV-BLR", "heavy_rainfall", 12.96, 77.56, 285, 11, 30, 84, 7.8, 45, "Bengaluru extreme rainfall cell"),
        _aimed("EV-BOB", "cyclone", 19.81, 85.83, 320, 13, 6, 144, 7.5, 110, "Bay of Bengal cyclonic storm"),
        _aimed("EV-MUM", "heavy_rainfall", 19.07, 72.90, 75, 10, 12, 72, 6.8, 45, "Konkan coast extreme rainfall"),
        _aimed("EV-RAJ", "heatwave", 27.90, 76.20, 60, 4, 60, 150, 6.0, 190, "Rajasthan-Delhi heatwave"),
        _aimed("EV-CHN", "heavy_rainfall", 13.08, 80.25, 280, 9, 108, 84, 7.8, 55, "North Tamil Nadu coastal rainfall"),
        _aimed("EV-GUW", "heavy_rainfall", 26.14, 91.74, 300, 8, 150, 78, 7.5, 60, "Assam-Meghalaya heavy rainfall"),
    ]


def random_events(rng: np.random.Generator, n: int, month: int, grid: Grid, prefix="EV-R") -> list[EventSpec]:
    """Random events with month-appropriate type frequencies (for ML training)."""
    winter = month in (11, 12, 1, 2)
    summer = month in (3, 4, 5, 6)
    probs = {
        "heavy_rainfall": 0.45,
        "heatwave": 0.30 if summer else 0.1,
        "cyclone": 0.2 if month in (4, 5, 6, 9, 10, 11, 12) else 0.08,
        "coldwave": 0.3 if winter else 0.05,
    }
    types = list(probs)
    p = np.array([probs[t] for t in types])
    p /= p.sum()
    out = []
    for i in range(n):
        t = str(rng.choice(types, p=p))
        if t == "cyclone":
            lat0, lon0 = rng.uniform(10, 17), rng.uniform(84, 91)
            heading = rng.uniform(290, 350)
            speed, radius = rng.uniform(8, 18), rng.uniform(80, 150)
        elif t == "heatwave":
            lat0, lon0 = rng.uniform(20, 29), rng.uniform(70, 84)
            heading, speed, radius = rng.uniform(0, 360), rng.uniform(2, 7), rng.uniform(120, 250)
        elif t == "coldwave":
            lat0, lon0 = rng.uniform(24, 32), rng.uniform(73, 88)
            heading, speed, radius = rng.uniform(90, 200), rng.uniform(3, 10), rng.uniform(100, 220)
        else:
            lat0 = rng.uniform(grid.lat_min + 2, grid.lat_max - 6)
            lon0 = rng.uniform(grid.lon_min + 3, grid.lon_max - 3)
            heading, speed, radius = rng.uniform(0, 360), rng.uniform(4, 20), rng.uniform(30, 90)
        out.append(
            EventSpec(
                id=f"{prefix}{i:03d}", type=t, lat0=float(lat0), lon0=float(lon0),
                speed_kmh=float(speed), heading_deg=float(heading),
                start_h=float(rng.uniform(0, settings.max_lead_hours - 60)),
                duration_h=float(rng.uniform(48, 150)), peak_z=float(rng.uniform(3.5, 8.5)),
                radius_km=float(radius), name=f"Random {t.replace('_', ' ')}",
            )
        )
    return out


# ------------------------------------------------------------------ noise helpers
def _correlated_noise(rng, shape, sigma_cells: float) -> np.ndarray:
    n = gaussian_filter(rng.standard_normal(shape).astype(np.float32), sigma_cells, mode="wrap")
    return n / (n.std() + 1e-6)


# ------------------------------------------------------------- forecast generator
@dataclass
class ForecastBundle:
    grid: Grid
    month: int
    lead_hours: np.ndarray            # (T,)
    fields: dict                      # var -> float32 (M, T, ny, nx) physical units (may contain NaN)
    truth: list = field(default_factory=list)  # list of EventSpec
    source: str = "synthetic"


def generate_forecast(
    grid: Grid,
    month: int,
    events: list[EventSpec],
    members: int = settings.ensemble_members,
    max_lead: int = settings.max_lead_hours,
    step: int = settings.step_hours,
    seed: int = 0,
    missing_rate: float = 0.001,
) -> ForecastBundle:
    """NEPS-like ensemble forecast with injected moving extreme events."""
    rng = np.random.default_rng(seed)
    clim = climatology(grid, month)
    leads = np.arange(0, max_lead + 1, step)
    T, (ny, nx) = len(leads), grid.shape
    fields = {v: np.empty((members, T, ny, nx), dtype=np.float32) for v in VARIABLES}

    # event anomaly (z units) per member per step, per variable
    ev_z = {v: np.zeros((members, T, ny, nx), dtype=np.float32) for v in VARIABLES}
    member_dir = rng.standard_normal((len(events), members, 2))  # coherent position error
    member_amp = rng.standard_normal((len(events), members))
    for ei, ev in enumerate(events):
        sig = EVENT_SIGNATURE[ev.type]
        for ti, h in enumerate(leads):
            base_amp = ev.intensity(h)
            if base_amp <= 0:
                continue
            lat_c, lon_c = ev.position(h)
            spread_km = 5 + 0.6 * h
            for m in range(members):
                dx, dy = member_dir[ei, m] * spread_km
                lat_m = lat_c + dy / 111.32
                lon_m = lon_c + dx / (111.32 * math.cos(math.radians(lat_c)))
                amp = base_amp * math.exp(member_amp[ei, m] * (0.08 + 0.0008 * h))
                x, y = to_local_km(grid.LAT, grid.LON, lat_m, lon_m)
                # elliptical footprint elongated along motion
                hdg = math.radians(ev.heading_deg)
                along = x * math.sin(hdg) + y * math.cos(hdg)
                across = x * math.cos(hdg) - y * math.sin(hdg)
                r = ev.radius_km
                blob = np.exp(-0.5 * ((along / (1.3 * r)) ** 2 + (across / r) ** 2)).astype(np.float32)
                for v in VARIABLES:
                    if sig[v]:
                        ev_z[v][m, ti] += amp * sig[v] * blob

    for v in VARIABLES:
        mean, std = clim[v]
        common = _correlated_noise(rng, (ny, nx), 4)
        for ti in range(T):
            if ti:
                common = 0.8 * common + 0.6 * _correlated_noise(rng, (ny, nx), 4)
            for m in range(members):
                member = _correlated_noise(rng, (ny, nx), 3)
                z = 0.65 * common + 0.45 * member + ev_z[v][m, ti]
                fields[v][m, ti] = to_physical(v, mean + std * z)
        if missing_rate > 0:
            mask = rng.random(fields[v].shape) < missing_rate
            fields[v][mask] = np.nan

    return ForecastBundle(grid=grid, month=month, lead_hours=leads, fields=fields, truth=list(events))


# ------------------------------------------------------------ population & assets
def population_density(lat, lon) -> np.ndarray:
    """People per km^2: rural baseline + Gaussian urban cores."""
    lat = np.asarray(lat, dtype=float)
    lon = np.asarray(lon, dtype=float)
    dens = np.full(lat.shape, 380.0)
    for _, _, clat, clon, pop, sig in CITIES:
        d = haversine_km(lat, lon, clat, clon)
        dens += pop / (2 * math.pi * sig**2) * np.exp(-0.5 * (d / sig) ** 2)
    return dens


_SCHOOL_KINDS = ["Govt. Primary School", "Govt. High School", "Public School", "PU College", "Engineering College", "Degree College"]
_HOSP_KINDS = ["Primary Health Centre", "Community Health Centre", "District Hospital", "Multispeciality Hospital"]
_RESCUE_KINDS = ["NDRF Team", "SDRF Unit", "Fire & Emergency Station", "Civil Defence Unit"]


def generate_assets(seed: int = 7) -> list[dict]:
    """OSM-like critical infrastructure around each reference city."""
    rng = np.random.default_rng(seed)
    assets = []
    for name, state, clat, clon, pop, sig in CITIES:
        code = CITY_CODE.get(name, name[:3].upper())
        n_school = int(0.012 * math.sqrt(pop))
        n_hosp = int(0.006 * math.sqrt(pop))
        n_rescue = max(3, int(0.0015 * math.sqrt(pop)))
        for kind, n, labels, spread in (
            ("school", n_school, _SCHOOL_KINDS, 0.9),
            ("hospital", n_hosp, _HOSP_KINDS, 0.8),
            ("rescue_team", n_rescue, _RESCUE_KINDS, 1.0),
        ):
            for i in range(n):
                dx, dy = rng.normal(0, sig * spread, 2)
                lat = clat + dy / 111.32
                lon = clon + dx / (111.32 * math.cos(math.radians(clat)))
                label = labels[int(rng.integers(len(labels)))]
                aid = f"{code}-{kind[:3].upper()}-{i + 1:03d}"
                cap = (
                    int(rng.integers(200, 3000)) if kind == "school"
                    else int(rng.integers(20, 800)) if kind == "hospital"
                    else int(rng.integers(15, 60))
                )
                assets.append({
                    "id": aid, "kind": kind, "name": f"{label}, {name} Zone {i % 8 + 1}",
                    "city": name, "state": state, "lat": round(float(lat), 5), "lon": round(float(lon), 5),
                    "capacity": cap,
                    "contact": f"{aid.lower()}@example.org",
                })
    return assets


def generate_vehicles(seed: int = 11, per_city: int = 25) -> list[dict]:
    """GPS-feed-like snapshot of moving vehicles near each city."""
    rng = np.random.default_rng(seed)
    kinds = [("bus", 35, 55), ("car", 30, 70), ("truck", 25, 50), ("two_wheeler", 20, 45)]
    out = []
    for name, _, clat, clon, _, sig in CITIES:
        for i in range(per_city):
            k, vmin, vmax = kinds[int(rng.integers(len(kinds)))]
            r = abs(rng.normal(0, sig * 1.8))
            ang = rng.uniform(0, 360)
            lat, lon = destination(clat, clon, ang, r)
            out.append({
                "id": f"VEH-{name[:3].upper()}-{i + 1:03d}", "kind": k, "city": name,
                "lat": round(lat, 5), "lon": round(lon, 5),
                "heading_deg": round(float(rng.uniform(0, 360)), 1),
                "speed_kmh": round(float(rng.uniform(vmin, vmax)), 1),
            })
    return out
