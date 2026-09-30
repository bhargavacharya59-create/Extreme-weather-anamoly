"""Population exposure from OFFICIAL Census of India 2011 data.

Two resolutions, finest first:
  1. Bengaluru: 198 BBMP wards with Census 2011 ward population
     (data/reference/bbmp_wards_census2011.geojson)
  2. Rest of India: Census 2011 district population / district area
     (data/reference/districts_density.csv). Points are assigned to the
     district with the nearest centroid; if the district polygons were fetched
     (data/raw/districts_simplified.geojson, by scripts/prepare_reference_data.py)
     exact point-in-polygon is used instead.

2011 counts are scaled to the present with WP_POP_PROJECTION_FACTOR
(default 1.18 ~ RGI Technical Group projection for 2026 / Census 2011, all-
India). Results are estimates at the resolution of the source data.
"""
from __future__ import annotations

import json
import math
import os
from functools import lru_cache

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from app.config import REPO_DIR
from app.geo import points_in_polygon, polygon_area_km2, ring_bbox, to_local_km

REF = REPO_DIR / "data" / "reference"
PROJECTION_FACTOR = float(os.getenv("WP_POP_PROJECTION_FACTOR", 1.18))
SOURCE_WARD = "Census 2011 · BBMP ward"
SOURCE_DISTRICT = "Census 2011 · district"


class PopulationService:
    def __init__(self):
        self.wards = []
        wpath = REF / "bbmp_wards_census2011.geojson"
        if wpath.exists():
            gj = json.loads(wpath.read_text())
            for f in gj["features"]:
                polys = [poly[0] for poly in f["geometry"]["coordinates"]]
                boxes = [ring_bbox(r) for r in polys]
                self.wards.append({**f["properties"], "polys": polys, "boxes": boxes})
        if self.wards:
            b = np.array([bx for w in self.wards for bx in w["boxes"]])
            self.ward_bbox = (b[:, 0].min(), b[:, 1].min(), b[:, 2].max(), b[:, 3].max())
        else:
            self.ward_bbox = None

        dpath = REF / "districts_density.csv"
        self.districts = pd.read_csv(dpath) if dpath.exists() else pd.DataFrame(
            columns=["state", "district", "lat", "lon", "area_km2", "population_2011", "density_2011"])
        if len(self.districts):
            x, y = to_local_km(self.districts["lat"].values, self.districts["lon"].values, 22.0, 80.0)
            self.tree = cKDTree(np.column_stack([x, y]))
        else:
            self.tree = None
        # optional exact district polygons (written by scripts/prepare_reference_data.py)
        self.dpolys = []
        ppath = REPO_DIR / "data" / "raw" / "districts_simplified.geojson"
        if ppath.exists() and len(self.districts):
            key = {(r.district, r.state): i for i, r in enumerate(self.districts.itertuples())}
            for f in json.loads(ppath.read_text())["features"]:
                i = key.get((f["properties"]["district"], f["properties"]["state"]))
                if i is None:
                    continue
                for poly in f["geometry"]["coordinates"]:
                    self.dpolys.append((i, poly[0], ring_bbox(poly[0])))
        self.available = bool(len(self.districts) or self.wards)

    # ----------------------------------------------------------------- lookup
    def _ward_index(self, lats, lons) -> np.ndarray:
        idx = np.full(lats.shape, -1, dtype=int)
        if not self.wards:
            return idx
        x0, y0, x1, y1 = self.ward_bbox
        cand = (lons >= x0) & (lons <= x1) & (lats >= y0) & (lats <= y1)
        if not cand.any():
            return idx
        for wi, w in enumerate(self.wards):
            for ring, (bx0, by0, bx1, by1) in zip(w["polys"], w["boxes"]):
                sub = cand & (idx < 0) & (lons >= bx0) & (lons <= bx1) & (lats >= by0) & (lats <= by1)
                if sub.any():
                    ins = points_in_polygon(lons[sub], lats[sub], ring)
                    where = np.nonzero(sub)[0][ins]
                    idx[where] = wi
        return idx

    def _district_index(self, lats, lons) -> np.ndarray:
        if self.dpolys:
            lats_f, lons_f = np.ravel(lats), np.ravel(lons)
            idx = np.full(lats_f.shape, -1, dtype=int)
            for i, ring, (x0, y0, x1, y1) in self.dpolys:
                sub = (idx < 0) & (lons_f >= x0) & (lons_f <= x1) & (lats_f >= y0) & (lats_f <= y1)
                if sub.any():
                    ins = points_in_polygon(lons_f[sub], lats_f[sub], ring)
                    idx[np.nonzero(sub)[0][ins]] = i
            return idx.reshape(np.shape(lats))
        if self.tree is None:
            return np.full(lats.shape, -1, dtype=int)
        x, y = to_local_km(lats, lons, 22.0, 80.0)
        d, i = self.tree.query(np.column_stack([np.ravel(x), np.ravel(y)]))
        i = i.reshape(np.shape(lats))
        # points far outside every district (open sea) -> no district
        radius = np.sqrt(self.districts["area_km2"].values[i] / np.pi) * 1.35 + 5
        return np.where(d.reshape(np.shape(lats)) <= radius, i, -1)

    def density(self, lats, lons):
        """People / km^2 (projected to present) and the source index arrays."""
        lats = np.asarray(lats, dtype=float)
        lons = np.asarray(lons, dtype=float)
        wi = self._ward_index(lats, lons)
        di = self._district_index(lats, lons)
        dens = np.zeros(lats.shape)
        if len(self.districts):
            dens = np.where(di >= 0, self.districts["density_2011"].values[np.clip(di, 0, None)], 0.0).astype(float)
        if self.wards:
            wd = np.array([w["density_2011"] for w in self.wards])
            m = wi >= 0
            dens[m] = wd[wi[m]]
        return dens * PROJECTION_FACTOR, wi, di

    # --------------------------------------------------------- zone exposure
    def in_polygon(self, ring, spacing_km: float = 0.25) -> dict:
        """Estimated residents inside a polygon ring [[lon, lat], ...]."""
        if not self.available:
            return {"total": 0, "sources": [], "wards": [], "districts": []}
        x0, y0, x1, y1 = ring_bbox(ring)
        lat0 = (y0 + y1) / 2
        dlat = spacing_km / 111.32
        dlon = spacing_km / (111.32 * math.cos(math.radians(lat0)))
        lats, lons = np.meshgrid(np.arange(y0, y1, dlat) + dlat / 2, np.arange(x0, x1, dlon) + dlon / 2, indexing="ij")
        lats, lons = lats.ravel(), lons.ravel()
        inside = points_in_polygon(lons, lats, ring)
        lats, lons = lats[inside], lons[inside]
        if lats.size == 0:
            return {"total": 0, "sources": [], "wards": [], "districts": []}
        dens, wi, di = self.density(lats, lons)
        cell = spacing_km ** 2
        people = dens * cell
        # rescale so the sampled area matches the exact polygon area
        area = polygon_area_km2(ring)
        people *= area / max(lats.size * cell, 1e-9)
        total = float(people.sum())

        wards = []
        for w in np.unique(wi[wi >= 0]):
            sel = wi == w
            ww = self.wards[w]
            wards.append({"ward_no": ww["ward_no"], "ward_name": ww["ward_name"],
                          "people": int(people[sel].sum()),
                          "share_of_ward": round(min(float(people[sel].sum()) / (ww["population_2011"] * PROJECTION_FACTOR), 1.0), 3)})
        districts = []
        for d in np.unique(di[(wi < 0) & (di >= 0)]):
            sel = (di == d) & (wi < 0)
            row = self.districts.iloc[int(d)]
            districts.append({"district": row["district"], "state": row["state"], "people": int(people[sel].sum())})
        male_share = self._male_share(wi)
        return {
            "total": int(round(total)),
            "male": int(round(total * male_share)),
            "female": int(round(total * (1 - male_share))),
            "households": int(round(total / 4.4)),
            "area_km2": round(area, 2),
            "sources": sorted({SOURCE_WARD if w >= 0 else SOURCE_DISTRICT for w in np.unique(wi)}),
            "wards": sorted(wards, key=lambda r: -r["people"]),
            "districts": sorted(districts, key=lambda r: -r["people"]),
            "projection_factor": PROJECTION_FACTOR,
        }

    def _male_share(self, wi) -> float:
        wi = wi[wi >= 0]
        if wi.size and self.wards:
            m = sum(self.wards[i]["male"] for i in np.unique(wi))
            t = sum(self.wards[i]["population_2011"] for i in np.unique(wi))
            if t:
                return m / t
        return 0.515  # Census 2011 all-India

    def wards_geojson(self) -> dict:
        feats = []
        for w in self.wards:
            props = {k: v for k, v in w.items() if k not in ("polys", "boxes")}
            feats.append({"type": "Feature", "properties": props,
                          "geometry": {"type": "MultiPolygon", "coordinates": [[r] for r in w["polys"]]}})
        return {"type": "FeatureCollection", "features": feats}

    def district_table(self, state: str | None = None, q: str | None = None, limit: int = 50) -> list[dict]:
        df = self.districts
        if state:
            df = df[df["state"].str.lower() == state.lower()]
        if q:
            df = df[df["district"].str.lower().str.contains(q.lower(), na=False)]
        return df.head(limit).assign(population_now=lambda d: (d["population_2011"] * PROJECTION_FACTOR).round().astype(int)).to_dict("records")


@lru_cache(maxsize=1)
def get_population() -> PopulationService:
    return PopulationService()
