"""Step 2 - Data preprocessing: quality control, gap filling, standardisation.

Output is a standardised-anomaly cube z = (x - clim_mean) / clim_std per
variable (precipitation in cube-root space), which is what detection works on.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.ndimage import uniform_filter

from app.data.synthetic import VARIABLES, ForecastBundle, to_model_space

# Physically plausible ranges used for QC (values outside -> treated as missing)
VALID_RANGE = {"precip": (0, 500), "t2m": (-40, 55), "wind": (0, 90), "mslp": (870, 1060)}


@dataclass
class Preprocessed:
    z: dict              # var -> (M, T, ny, nx) standardised anomalies
    z_mean: dict         # var -> (T, ny, nx) ensemble-mean anomaly
    qc: dict             # QC report


def _fill_nans(a: np.ndarray) -> tuple[np.ndarray, int]:
    """Fill isolated NaNs with the mean of their 3x3 neighbourhood; any
    remaining gaps (large holes) get the climatological value, i.e. z = 0."""
    n_missing = int(np.isnan(a).sum())
    if n_missing == 0:
        return a, 0
    # NaN-aware 3x3 mean over the two spatial axes only
    nan = np.isnan(a)
    size = (1,) * (a.ndim - 2) + (3, 3)
    s = uniform_filter(np.where(nan, 0.0, a), size=size, mode="nearest")
    c = uniform_filter((~nan).astype(np.float32), size=size, mode="nearest")
    with np.errstate(invalid="ignore", divide="ignore"):
        local = s / c
    return np.where(nan, local, a), n_missing


def standardise(bundle: ForecastBundle, clim: dict) -> Preprocessed:
    z, z_mean, qc = {}, {}, {"missing_filled": {}, "out_of_range": {}}
    for var in VARIABLES:
        x = bundle.fields[var].astype(np.float32)
        lo, hi = VALID_RANGE[var]
        bad = (x < lo) | (x > hi)
        qc["out_of_range"][var] = int(bad.sum())
        x = np.where(bad, np.nan, x)
        mean, std = clim[var]
        zz = (to_model_space(var, x) - mean) / std
        zz, n = _fill_nans(zz)
        zz = np.nan_to_num(zz, nan=0.0)
        qc["missing_filled"][var] = n
        z[var] = zz.astype(np.float32)
        z_mean[var] = zz.mean(axis=0).astype(np.float32)
    qc["members"] = int(next(iter(z.values())).shape[0])
    qc["lead_steps"] = int(len(bundle.lead_hours))
    return Preprocessed(z=z, z_mean=z_mean, qc=qc)
