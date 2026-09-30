"""Adapters for REAL datasets. Each returns the same structures the synthetic
generators return, so switching a source is a one-line change in
`app/service.py` (or set WP_FORECAST_SOURCE / WP_ASSET_SOURCE, see README).

Optional dependencies (install with `pip install -r requirements-realdata.txt`):
  xarray + netCDF4   ERA5 / IMDAA / NCUM / NEPS NetCDF files
  cfgrib             the same products as GRIB2
  imdlib             IMD gridded rainfall / temperature binaries

See docs/DATASETS.md for where to download each dataset.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from app.data.synthetic import VARIABLES, ForecastBundle, Grid, to_model_space

# Common variable names across ECMWF / NCMRWF products -> ours
_NAME_MAP = {
    "precip": ["tp", "apcp", "precipitation_amount", "APCP_surface", "rain"],
    "t2m": ["t2m", "2t", "air_temperature", "TMP_2maboveground", "tmax"],
    "wind": ["si10", "ws10", "wind_speed"],
    "u10": ["u10", "10u", "UGRD_10maboveground"],
    "v10": ["v10", "10v", "VGRD_10maboveground"],
    "mslp": ["msl", "prmsl", "PRMSL_meansealevel", "air_pressure_at_mean_sea_level"],
}


def _require(module: str):
    try:
        return __import__(module)
    except ImportError as e:  # pragma: no cover - optional path
        raise ImportError(
            f"'{module}' is needed to read real data. Install it with: pip install -r requirements-realdata.txt"
        ) from e


def _pick(ds, key):
    for name in _NAME_MAP[key]:
        if name in ds.variables:
            return ds[name]
    return None


def _to_units(var: str, da):
    units = str(da.attrs.get("units", "")).lower()
    if var == "t2m" and units in {"k", "kelvin"}:
        return da - 273.15
    if var == "mslp" and units in {"pa", "pascal"}:
        return da / 100.0
    if var == "precip" and units in {"m", "metre", "meters"}:
        return da * 1000.0
    return da


def _regrid(xr, da, grid: Grid):
    lat = "latitude" if "latitude" in da.dims else "lat"
    lon = "longitude" if "longitude" in da.dims else "lon"
    return da.interp({lat: xr.DataArray(grid.lats, dims="lat_out"), lon: xr.DataArray(grid.lons, dims="lon_out")})


def load_ensemble_forecast(path: str | Path, grid: Grid | None = None, month: int | None = None) -> ForecastBundle:
    """Load an NCUM / NEPS / ECMWF-ENS forecast (NetCDF or GRIB2).

    Expected dims: [number (member)], step (lead time), latitude, longitude.
    Accumulated precipitation is de-accumulated into 6-hourly totals.
    """
    xr = _require("xarray")
    path = Path(path)
    engine = "cfgrib" if path.suffix in {".grib", ".grib2", ".grb2"} else None
    ds = xr.open_dataset(path, engine=engine)
    grid = grid or Grid()

    fields = {}
    for var in VARIABLES:
        if var == "wind":
            da = _pick(ds, "wind")
            if da is None:
                u, v = _pick(ds, "u10"), _pick(ds, "v10")
                if u is None or v is None:
                    raise KeyError("No 10 m wind found (need si10 or u10+v10)")
                da = np.hypot(u, v)
        else:
            da = _pick(ds, var)
            if da is None:
                raise KeyError(f"Variable for '{var}' not found. Looked for {_NAME_MAP[var]}")
            da = _to_units(var, da)
        if "number" not in da.dims:
            da = da.expand_dims("number")
        step_dim = "step" if "step" in da.dims else "time"
        da = _regrid(xr, da, grid).transpose("number", step_dim, "lat_out", "lon_out")
        arr = da.values.astype(np.float32)
        if var == "precip" and str(ds[_NAME_MAP["precip"][0]].attrs.get("GRIB_stepType", "accum")) == "accum":
            arr = np.clip(np.diff(arr, axis=1, prepend=arr[:, :1]), 0, None)
        fields[var] = arr
        steps = da[step_dim].values

    if np.issubdtype(np.asarray(steps).dtype, np.timedelta64):
        leads = (np.asarray(steps) / np.timedelta64(1, "h")).astype(int)
    else:
        leads = np.arange(len(steps)) * 6
    if month is None:
        t0 = ds["time"].values if "time" in ds else None
        month = int(np.datetime64(t0.ravel()[0], "M").astype(int) % 12 + 1) if t0 is not None else 1
    return ForecastBundle(grid=grid, month=month, lead_hours=leads, fields=fields, source=str(path.name))


def load_reanalysis_climatology(path: str | Path, month: int, grid: Grid | None = None) -> dict:
    """Monthly mean/std per cell from ERA5 or IMDAA hourly/6-hourly reanalysis.

    Download e.g. 1991-2020 single-levels (tp, 2t, 10u, 10v, msl) for the India
    box from the Copernicus CDS. Returns the same dict as `synthetic.climatology`.
    """
    xr = _require("xarray")
    ds = xr.open_mfdataset(str(path)) if "*" in str(path) else xr.open_dataset(path)
    grid = grid or Grid()
    tdim = "valid_time" if "valid_time" in ds.dims else "time"
    ds = ds.sel({tdim: ds[tdim].dt.month == month})
    out = {}
    for var in VARIABLES:
        if var == "wind":
            da = np.hypot(_pick(ds, "u10"), _pick(ds, "v10"))
        else:
            da = _to_units(var, _pick(ds, var))
        if var == "precip":
            # hourly totals -> 6-hourly totals
            da = da.resample({tdim: "6h"}).sum()
        da = _regrid(xr, da, grid)
        x = to_model_space(var, da.values.astype(np.float32))
        out[var] = (np.nanmean(x, axis=0).astype(np.float32), (np.nanstd(x, axis=0) + 1e-3).astype(np.float32))
    return out


def load_imd_gridded_rainfall(folder: str | Path, start_year: int, end_year: int):
    """IMD 0.25 deg daily gridded rainfall via imdlib (for validation / climatology)."""
    imdlib = _require("imdlib")
    return imdlib.open_data("rain", start_year, end_year, "yearwise", str(folder)).get_xarray()


_OSM_KIND = {
    ("amenity", "school"): "school",
    ("amenity", "college"): "school",
    ("amenity", "university"): "school",
    ("amenity", "kindergarten"): "school",
    ("amenity", "hospital"): "hospital",
    ("amenity", "clinic"): "hospital",
    ("healthcare", "hospital"): "hospital",
    ("amenity", "fire_station"): "rescue_team",
    ("emergency", "ambulance_station"): "rescue_team",
    ("amenity", "police"): "rescue_team",
}


def load_osm_assets(geojson_path: str | Path, city: str = "") -> list[dict]:
    """Critical infrastructure from an OpenStreetMap GeoJSON export.

    Produce one with Overpass Turbo (query in docs/DATASETS.md) or `osmium export`
    on a Geofabrik India extract. Polygons are reduced to their vertex centroid.
    """
    gj = json.loads(Path(geojson_path).read_text())
    assets = []
    for i, feat in enumerate(gj.get("features", [])):
        props = feat.get("properties", {}) or {}
        tags = props.get("tags", props)
        kind = next((k for (key, val), k in _OSM_KIND.items() if tags.get(key) == val), None)
        if not kind:
            continue
        geom = feat.get("geometry") or {}
        coords = np.asarray(_flatten(geom.get("coordinates", [])), dtype=float).reshape(-1, 2)
        if coords.size == 0:
            continue
        lon, lat = coords.mean(axis=0)
        assets.append({
            "id": f"OSM-{props.get('@id', props.get('id', i))}".replace("/", "-"),
            "kind": kind, "name": tags.get("name") or f"Unnamed {kind}",
            "city": city or tags.get("addr:city", ""), "state": tags.get("addr:state", ""),
            "lat": round(float(lat), 6), "lon": round(float(lon), 6),
            "capacity": int(tags.get("capacity", 0) or tags.get("beds", 0) or 0) if str(tags.get("capacity", tags.get("beds", "0"))).isdigit() else 0,
            "contact": tags.get("email") or tags.get("contact:email") or tags.get("phone") or "",
        })
    return assets


def _flatten(c):
    if not c:
        return []
    if isinstance(c[0], (int, float)):
        return [c[:2]]
    out = []
    for x in c:
        out.extend(_flatten(x))
    return out


class GriddedPopulation:
    """Population density from a CSV (lat, lon, density_per_km2), e.g. WorldPop
    1 km aggregated with `gdal2xyz`. Nearest-cell lookup."""

    def __init__(self, csv_path: str | Path):
        import pandas as pd

        df = pd.read_csv(csv_path)
        self.lats = np.sort(df["lat"].unique())
        self.lons = np.sort(df["lon"].unique())
        grid = df.pivot_table(index="lat", columns="lon", values="density_per_km2").reindex(index=self.lats, columns=self.lons)
        self.values = grid.fillna(0).to_numpy()

    def __call__(self, lat, lon):
        i = np.clip(np.searchsorted(self.lats, lat), 0, len(self.lats) - 1)
        j = np.clip(np.searchsorted(self.lons, lon), 0, len(self.lons) - 1)
        return self.values[i, j]
