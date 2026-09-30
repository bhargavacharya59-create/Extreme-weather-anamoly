"""Small, dependency-free geodesy helpers (numpy only).

Impact zones are a few km across, so a local equirectangular projection around
the zone centre is accurate to well under 1%.
"""
from __future__ import annotations

import math

import numpy as np

EARTH_R_KM = 6371.0088
KM_PER_DEG_LAT = 111.32

COMPASS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]


def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * EARTH_R_KM * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def bearing_deg(lat1, lon1, lat2, lon2):
    """Initial bearing from point 1 to point 2, degrees clockwise from north."""
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    dlon = lon2 - lon1
    x = np.sin(dlon) * np.cos(lat2)
    y = np.cos(lat1) * np.sin(lat2) - np.sin(lat1) * np.cos(lat2) * np.cos(dlon)
    return (np.degrees(np.arctan2(x, y)) + 360.0) % 360.0


def destination(lat, lon, bearing, dist_km):
    lat_r, lon_r, brg = math.radians(lat), math.radians(lon), math.radians(bearing)
    d = dist_km / EARTH_R_KM
    lat2 = math.asin(math.sin(lat_r) * math.cos(d) + math.cos(lat_r) * math.sin(d) * math.cos(brg))
    lon2 = lon_r + math.atan2(math.sin(brg) * math.sin(d) * math.cos(lat_r), math.cos(d) - math.sin(lat_r) * math.sin(lat2))
    return math.degrees(lat2), (math.degrees(lon2) + 540) % 360 - 180


def compass(bearing: float) -> str:
    return COMPASS[int((bearing % 360) / 22.5 + 0.5) % 16]


def to_local_km(lat, lon, lat0, lon0):
    """Equirectangular projection to (x east km, y north km) around (lat0, lon0)."""
    x = (np.asarray(lon) - lon0) * KM_PER_DEG_LAT * math.cos(math.radians(lat0))
    y = (np.asarray(lat) - lat0) * KM_PER_DEG_LAT
    return x, y


def from_local_km(x, y, lat0, lon0):
    lat = lat0 + np.asarray(y) / KM_PER_DEG_LAT
    lon = lon0 + np.asarray(x) / (KM_PER_DEG_LAT * math.cos(math.radians(lat0)))
    return lat, lon


def ellipse_polygon(lat0, lon0, a_km, b_km, heading_deg=0.0, offset_km=0.0, n=48):
    """Ellipse with semi-major axis a_km along `heading_deg`, centre shifted
    `offset_km` forward along the heading. Returns closed ring [[lon, lat], ...]."""
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    along = a_km * np.cos(t) + offset_km
    across = b_km * np.sin(t)
    h = math.radians(heading_deg)
    # heading is clockwise from north: along-axis unit vector = (sin h, cos h)
    x = along * math.sin(h) + across * math.cos(h)
    y = along * math.cos(h) - across * math.sin(h)
    lat, lon = from_local_km(x, y, lat0, lon0)
    ring = [[round(float(lo), 5), round(float(la), 5)] for la, lo in zip(lat, lon)]
    ring.append(ring[0])
    return ring


def points_in_polygon(lons, lats, ring) -> np.ndarray:
    """Vectorised even-odd ray casting. ring = [[lon, lat], ...]."""
    lons = np.asarray(lons, dtype=float)
    lats = np.asarray(lats, dtype=float)
    poly = np.asarray(ring, dtype=float)
    inside = np.zeros(lons.shape, dtype=bool)
    xj, yj = poly[-1]
    for xi, yi in poly:
        cond = (yi > lats) != (yj > lats)
        with np.errstate(divide="ignore", invalid="ignore"):
            xcross = (xj - xi) * (lats - yi) / (yj - yi) + xi
        inside ^= cond & (lons < xcross)
        xj, yj = xi, yi
    return inside


def polygon_area_km2(ring) -> float:
    poly = np.asarray(ring, dtype=float)
    lat0, lon0 = poly[:, 1].mean(), poly[:, 0].mean()
    x, y = to_local_km(poly[:, 1], poly[:, 0], lat0, lon0)
    return float(abs(0.5 * np.sum(x[:-1] * y[1:] - x[1:] * y[:-1])))


def ring_bbox(ring):
    poly = np.asarray(ring, dtype=float)
    return poly[:, 0].min(), poly[:, 1].min(), poly[:, 0].max(), poly[:, 1].max()
