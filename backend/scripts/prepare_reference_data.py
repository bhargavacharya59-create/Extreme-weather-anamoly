"""Download and prepare the OFFICIAL reference datasets used for population
exposure.

Sources (all public):
  * Census of India 2011, district-level Primary Census Abstract figures
      mirror: github.com/nishusharma1608/India-Census-2011-Analysis
      (india-districts-census-2011.csv, 640 districts)
  * Bengaluru BBMP ward boundaries (2012 delimitation) with Census 2011 ward
    population, DataMeet Municipal_Spatial_Data (CC BY-SA 2.5 India)
      github.com/datameet/Municipal_Spatial_Data/tree/master/Bangalore
  * District boundaries (for area / density), github.com/geohacker/india
    (district/india_district.geojson). Used only to derive district area and
    centroid; the polygons themselves are NOT committed to this repo.

Outputs (committed, small):
  data/reference/census2011_districts.csv   district population table
  data/reference/districts_density.csv       centroid, area, population, density
  data/reference/bbmp_wards_census2011.geojson  198 wards, simplified polygons
Also writes (NOT committed, see .gitignore):
  data/raw/districts_simplified.geojson   district polygons for exact lookups

Run:  python -m scripts.prepare_reference_data   (needs `git` and internet)
"""
from __future__ import annotations

import difflib
import json
import math
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "reference"
RAW = ROOT / "data" / "raw"

REPOS = {
    "census": ("https://github.com/nishusharma1608/India-Census-2011-Analysis", None),
    "wards": ("https://github.com/datameet/Municipal_Spatial_Data", "Bangalore"),
    "districts": ("https://github.com/geohacker/india", None),
}

STATE_ALIASES = {
    "orissa": "odisha", "uttaranchal": "uttarakhand", "pondicherry": "puducherry",
    "andaman and nicobar": "andaman and nicobar islands", "nct of delhi": "delhi",
    "dadra and nagar haveli": "dadra and nagar haveli", "daman and diu": "daman and diu",
}


# Boundary (GADM, ~2001 names) -> Census 2011 district names, for renamed/split districts.
DISTRICT_ALIASES = {
    "bangalore urban": ["bangalore"], "greater bombay": ["mumbai", "mumbai suburban"],
    "cuddapah": ["y s r"], "nellore": ["sri potti sriramulu nellore"], "north cachar hills": ["dima hasao"],
    "bhabua": ["kaimur"], "dantewada": ["dakshin bastar dantewada"], "kanker": ["uttar bastar kanker"],
    "kawardha": ["kabeerdham"], "dahod": ["dohad"], "east nimar": ["khandwa"], "west nimar": ["khargone"],
    "east imphal": ["imphal east"], "west imphal": ["imphal west"], "sonepur": ["subarnapur"],
    "nawan shehar": ["shahid bhagat singh nagar"], "north sikkim": ["north"], "south sikkim": ["south"],
    "west sikkim": ["west"], "east sikkim": ["east"], "hathras": ["mahamaya nagar"], "lakhimpur kheri": ["kheri"],
    "east midnapore": ["purba medinipur"], "west midnapore": ["paschim medinipur"],
    "north parganas": ["north twenty four parganas"], "south parganas": ["south twenty four parganas"],
    "ladakh": ["leh"], "andaman islands": ["north and middle andaman", "south andaman"], "nicobar islands": ["nicobars"],
    "kavaratti": ["lakshadweep"],
}


def _norm(s: str) -> str:
    s = str(s).lower().replace("&", "and")
    s = re.sub(r"\(.*?\)", "", s)
    s = re.sub(r"[^a-z ]", " ", s)
    s = re.sub(r"\b(district|dist)\b", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return STATE_ALIASES.get(s, s)


def _clone(url: str, dest: Path, sparse: str | None):
    if dest.exists():
        return
    cmd = ["git", "clone", "-q", "--depth", "1"]
    if sparse:
        cmd += ["--filter=blob:none", "--sparse"]
    subprocess.run(cmd + [url, str(dest)], check=True)
    if sparse:
        subprocess.run(["git", "-C", str(dest), "sparse-checkout", "set", sparse], check=True)


# ---------------------------------------------------------------- geometry
def _rings(geom):
    if geom["type"] == "Polygon":
        return [geom["coordinates"]]
    if geom["type"] == "MultiPolygon":
        return geom["coordinates"]
    return []


def _ring_area_centroid(ring):
    pts = np.asarray(ring, dtype=float)
    lat0 = pts[:, 1].mean()
    x = pts[:, 0] * 111.32 * math.cos(math.radians(lat0))
    y = pts[:, 1] * 111.32
    cross = x[:-1] * y[1:] - x[1:] * y[:-1]
    a = 0.5 * cross.sum()
    if abs(a) < 1e-12:
        return 0.0, pts[:, 0].mean(), pts[:, 1].mean()
    cx = ((x[:-1] + x[1:]) * cross).sum() / (6 * a)
    cy = ((y[:-1] + y[1:]) * cross).sum() / (6 * a)
    return abs(a), cx / (111.32 * math.cos(math.radians(lat0))), cy / 111.32


def polygon_area_centroid(geom):
    tot, sx, sy = 0.0, 0.0, 0.0
    for poly in _rings(geom):
        a, cx, cy = _ring_area_centroid(poly[0])
        for hole in poly[1:]:
            a -= _ring_area_centroid(hole)[0]
        tot += a
        sx += a * cx
        sy += a * cy
    return tot, (sx / tot if tot else 0), (sy / tot if tot else 0)


def _rdp(pts, eps):
    """Ramer-Douglas-Peucker line simplification."""
    if len(pts) < 3:
        return pts
    start, end = pts[0], pts[-1]
    d = end - start
    n = np.hypot(*d)
    if n == 0:
        dist = np.hypot(*(pts - start).T)
    else:
        dist = np.abs(d[0] * (start[1] - pts[:, 1]) - d[1] * (start[0] - pts[:, 0])) / n
    i = int(np.argmax(dist))
    if dist[i] > eps:
        left = _rdp(pts[: i + 1], eps)
        right = _rdp(pts[i:], eps)
        return np.vstack([left[:-1], right])
    return np.vstack([start, end])


def simplify_geom(geom, eps=0.0004):
    out = []
    for poly in _rings(geom):
        new_poly = []
        for ring in poly:
            r = _rdp(np.asarray(ring, dtype=float), eps)
            if len(r) >= 4:
                new_poly.append([[round(x, 5), round(y, 5)] for x, y in r])
        if new_poly:
            out.append(new_poly)
    return {"type": "MultiPolygon", "coordinates": out}


# ---------------------------------------------------------------- main steps
def build_census(census_csv: Path) -> pd.DataFrame:
    df = pd.read_csv(census_csv)
    keep = ["District code", "State name", "District name", "Population", "Male", "Female",
            "Literate", "Households", "Urban_Households", "Rural_Households",
            "Age_Group_0_29", "Age_Group_30_49", "Age_Group_50"]
    df = df[keep].rename(columns={
        "District code": "district_code", "State name": "state", "District name": "district",
        "Population": "population_2011", "Male": "male", "Female": "female", "Literate": "literate",
        "Households": "households", "Urban_Households": "urban_households",
        "Rural_Households": "rural_households", "Age_Group_0_29": "age_0_29",
        "Age_Group_30_49": "age_30_49", "Age_Group_50": "age_50_plus"})
    df["state"] = df["state"].str.title()
    return df


def build_density(census: pd.DataFrame, districts_geojson: Path) -> pd.DataFrame:
    gj = json.loads(districts_geojson.read_text())
    polys = []
    for f in gj["features"]:
        p = f["properties"]
        area, lon, lat = polygon_area_centroid(f["geometry"])
        polys.append({"state_n": _norm(p["NAME_1"]), "district_n": _norm(p["NAME_2"]),
                      "state": p["NAME_1"], "district": p["NAME_2"],
                      "lat": round(lat, 4), "lon": round(lon, 4), "area_km2": round(area, 1)})
    P = pd.DataFrame(polys)
    census = census.copy()
    census["state_n"] = census["state"].map(_norm)
    census["district_n"] = census["district"].map(_norm)

    P["population_2011"] = np.nan
    P["census_match"] = ""
    used = set()

    def take(i, rows):
        P.at[i, "population_2011"] = float(rows.population_2011.sum())
        P.at[i, "census_match"] = "; ".join(f"{r.district} ({r.district_code})" for r in rows.itertuples())
        used.update(int(c) for c in rows.district_code)

    # pass 1: explicit aliases and exact names (never fuzzy first: "Bangalore Urban" != "Bangalore Rural")
    pending = []
    for i, row in P.iterrows():
        cands = census[census["state_n"] == row.state_n]
        if cands.empty:
            best = difflib.get_close_matches(row.state_n, census["state_n"].unique(), n=1, cutoff=0.7)
            cands = census[census["state_n"] == best[0]] if best else cands
        names = DISTRICT_ALIASES.get(row.district_n)
        if names:
            rows = cands[cands["district_n"].isin(names)]
            if len(rows):
                take(i, rows)
                continue
        rows = cands[cands["district_n"] == row.district_n]
        if len(rows) == 1:
            take(i, rows)
            continue
        pending.append((i, row, cands))
    # pass 2: fuzzy match against census districts not used yet
    for i, row, cands in pending:
        free = cands[~cands["district_code"].isin(used)]
        m = difflib.get_close_matches(row.district_n, free["district_n"].tolist(), n=1, cutoff=0.75)
        if m:
            take(i, free[free["district_n"] == m[0]].iloc[:1])

    # spread population of census districts that have no polygon (districts created
    # after the boundary set was drawn) over their state's unmatched polygons (or all).
    for st, grp in census.groupby("state_n"):
        rest = grp[~grp["district_code"].isin(used)]["population_2011"].sum()
        mask = P["state_n"] == st
        if not mask.any():
            best = difflib.get_close_matches(st, P["state_n"].unique(), n=1, cutoff=0.7)
            mask = P["state_n"] == (best[0] if best else "__none__")
        if not mask.any() or rest <= 0:
            continue
        empty = mask & P["population_2011"].isna()
        target = empty if empty.any() else mask
        w = P.loc[target, "area_km2"] / P.loc[target, "area_km2"].sum()
        P.loc[target, "population_2011"] = P.loc[target, "population_2011"].fillna(0) + rest * w
    P["population_2011"] = P["population_2011"].fillna(0).round().astype(int)
    P["density_2011"] = (P["population_2011"] / P["area_km2"].clip(lower=1)).round(1)
    return P.drop(columns=["state_n", "district_n"])


def build_wards(wards_geojson: Path) -> dict:
    gj = json.loads(wards_geojson.read_text())
    feats = []
    for f in gj["features"]:
        p = f["properties"]
        feats.append({
            "type": "Feature",
            "properties": {
                "ward_no": int(p["WARD_NO"]), "ward_name": p["WARD_NAME"].strip(),
                "assembly": p.get("ASS_CONST1"), "population_2011": int(p["POP_TOTAL"]),
                "male": int(p["POP_M"]), "female": int(p["POP_F"]),
                "sc": int(p.get("POP_SC") or 0), "st": int(p.get("POP_ST") or 0),
                "area_km2": float(p["AREA_SQ_KM"]),
                "density_2011": round(p["POP_TOTAL"] / max(p["AREA_SQ_KM"], 0.01), 1),
            },
            "geometry": simplify_geom(f["geometry"], eps=0.00015),
        })
    return {"type": "FeatureCollection",
            "properties": {"source": "Census of India 2011 via DataMeet Municipal_Spatial_Data (CC BY-SA 2.5 IN)",
                           "city": "Bengaluru (BBMP, 2012 wards)"},
            "features": feats}


def main(workdir: str | None = None):
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="wp_ref_"))
    paths = {}
    for key, (url, sparse) in REPOS.items():
        dest = tmp / key
        print(f"fetching {url} ...")
        _clone(url, dest, sparse)
        paths[key] = dest

    census = build_census(paths["census"] / "india-districts-census-2011.csv")
    census.to_csv(OUT / "census2011_districts.csv", index=False)
    print(f"census districts: {len(census)}  total population 2011: {census.population_2011.sum():,}")

    dens = build_density(census, paths["districts"] / "district" / "india_district.geojson")
    dens.to_csv(OUT / "districts_density.csv", index=False)
    # Optional, NOT committed (GADM-derived boundaries): simplified district polygons with
    # density, so population lookups use exact point-in-polygon instead of nearest centroid.
    RAW.mkdir(parents=True, exist_ok=True)
    gj = json.loads((paths["districts"] / "district" / "india_district.geojson").read_text())
    feats = []
    for f, (_, row) in zip(gj["features"], dens.iterrows()):
        feats.append({"type": "Feature", "properties": {"district": row.district, "state": row.state,
                      "density_2011": row.density_2011}, "geometry": simplify_geom(f["geometry"], eps=0.004)})
    (RAW / "districts_simplified.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, separators=(",", ":")))
    print(f"district polygons: {len(dens)}  matched: {(dens.census_match != '').sum()}  "
          f"population carried: {dens.population_2011.sum():,}")

    wards = build_wards(paths["wards"] / "Bangalore" / "BBMP_oldWards.geojson")
    (OUT / "bbmp_wards_census2011.geojson").write_text(json.dumps(wards, separators=(",", ":")))
    print(f"BBMP wards: {len(wards['features'])}  population 2011: "
          f"{sum(f['properties']['population_2011'] for f in wards['features']):,}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
