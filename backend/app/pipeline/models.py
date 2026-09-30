"""ML models: event-type classifier, severity classifier, anomaly scorer and
trajectory model. Trained on labelled synthetic hindcasts (plus any field
feedback stored by the continuous-learning loop).

XGBoost is used when installed, otherwise scikit-learn's
HistGradientBoostingClassifier (same role, no extra dependency).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor, HistGradientBoostingClassifier, IsolationForest
from sklearn.metrics import accuracy_score, classification_report, f1_score, precision_score, recall_score
from sklearn.model_selection import GroupShuffleSplit

from app.config import settings
from app.data.synthetic import Grid, generate_forecast, climatology, random_events
from app.geo import haversine_km
from app.pipeline.detection import FEATURE_NAMES, AnomalyObject, detect, rule_based_type, severity_from_z
from app.pipeline.preprocess import standardise

TYPE_CLASSES = ["noise", "heavy_rainfall", "heatwave", "cyclone", "coldwave"]
SEV_CLASSES = ["Low", "Moderate", "High"]

try:  # optional
    from xgboost import XGBClassifier  # type: ignore
except Exception:  # pragma: no cover
    XGBClassifier = None


def _make_classifier(n_classes: int):
    if XGBClassifier is not None:
        return XGBClassifier(n_estimators=250, max_depth=5, learning_rate=0.08, subsample=0.9,
                             colsample_bytree=0.9, objective="multi:softprob", num_class=n_classes)
    return HistGradientBoostingClassifier(max_iter=250, learning_rate=0.08, max_depth=6, random_state=0)


# ------------------------------------------------------------------ training data
def label_objects(objects: list[AnomalyObject], truth) -> tuple[list[int], list[int]]:
    """Match each detected object to the ground-truth event active at that lead."""
    y_type, y_sev = [], []
    for o in objects:
        best, best_d = None, 1e9
        for ev in truth:
            inten = ev.intensity(o.lead_h)
            if inten < 2.0:
                continue
            la, lo = ev.position(o.lead_h)
            d = float(haversine_km(o.lat, o.lon, la, lo))
            if d < max(1.6 * ev.radius_km, 150) and d < best_d:
                best, best_d = (ev, inten), d
        if best is None:
            y_type.append(0)
            y_sev.append(0)
        else:
            ev, inten = best
            y_type.append(TYPE_CLASSES.index(ev.type))
            y_sev.append(2 if inten >= 5.5 else 1 if inten >= 4.0 else 0)
    return y_type, y_sev


def build_training_set(n_scenarios: int = 24, seed: int = 1000, members: int = 4, verbose: bool = True):
    """Simulate labelled hindcasts across all months."""
    grid = Grid()
    rng = np.random.default_rng(seed)
    X, yt, ys, meta = [], [], [], []
    for i in range(n_scenarios):
        month = int(i % 12) + 1
        events = random_events(rng, int(rng.integers(4, 9)), month, grid, prefix=f"TR{i:02d}-")
        bundle = generate_forecast(grid, month, events, members=members, seed=seed + i)
        pre = standardise(bundle, climatology(grid, month))
        objs = detect(bundle, pre)
        t, s = label_objects(objs, events)
        X += [o.feature_vector() for o in objs]
        yt += t
        ys += s
        meta += [{"scenario": i, "lead_h": o.lead_h} for o in objs]
        if verbose:
            print(f"  scenario {i + 1}/{n_scenarios}: month={month} events={len(events)} objects={len(objs)}")
    return np.asarray(X, dtype=np.float32), np.asarray(yt), np.asarray(ys), meta


def build_trajectory_set(n_tracks: int = 3000, seed: int = 5):
    """Synthetic storm tracks with curvature/acceleration for the path model.

    Input: last 3 displacements (km east/north per 6 h) + lat, lon.
    Target: next displacement. Learns recurvature (e.g. Bay-of-Bengal storms
    turning north-east) that a constant-velocity extrapolation misses.
    """
    rng = np.random.default_rng(seed)
    X, Y = [], []
    for _ in range(n_tracks):
        lat, lon = rng.uniform(8, 30), rng.uniform(70, 95)
        speed = rng.uniform(20, 120)                # km per 6 h
        hdg = rng.uniform(0, 360)
        turn = rng.normal(0, 4)                     # deg per step
        accel = rng.normal(0, 3)
        hist = []
        for _ in range(8):
            # climatological recurvature: north of 18N storms turn clockwise (towards NE)
            turn_eff = turn + (3.0 if lat > 18 else 0.0)
            hdg = (hdg + turn_eff + rng.normal(0, 2)) % 360
            speed = max(5, speed + accel + rng.normal(0, 2))
            dx, dy = speed * np.sin(np.radians(hdg)), speed * np.cos(np.radians(hdg))
            hist.append((dx, dy, lat, lon))
            lat += dy / 111.32
            lon += dx / (111.32 * np.cos(np.radians(lat)))
        for j in range(3, len(hist)):
            prev = hist[j - 3:j]
            X.append([p[0] for p in prev] + [p[1] for p in prev] + [prev[-1][2], prev[-1][3]])
            Y.append(hist[j][:2])
    return np.asarray(X), np.asarray(Y)


# ------------------------------------------------------------------ model bundle
class ModelBundle:
    def __init__(self):
        self.type_clf = None
        self.sev_clf = None
        self.iso = None
        self.traj_x = None
        self.traj_y = None
        self.metrics: dict = {}
        self.trained_at: str | None = None

    # ---- training
    def fit(self, X, y_type, y_sev, groups=None, verbose=True):
        # Event-based hold-out: whole simulated scenarios go to test, so near-duplicate
        # objects from the same weather situation never sit on both sides of the split.
        groups = np.arange(len(X)) if groups is None else np.asarray(groups)
        tr, te = next(GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=0).split(X, y_type, groups))
        Xtr, Xte, yt_tr, yt_te, ys_tr, ys_te = X[tr], X[te], y_type[tr], y_type[te], y_sev[tr], y_sev[te]
        self.type_clf = _make_classifier(len(TYPE_CLASSES)).fit(Xtr, yt_tr)
        real = yt_tr > 0
        self.sev_clf = _make_classifier(len(SEV_CLASSES)).fit(Xtr[real], ys_tr[real])
        # unsupervised: how different is an object from typical noise blobs?
        noise = Xtr[yt_tr == 0]
        self.iso = IsolationForest(n_estimators=200, random_state=0).fit(noise if len(noise) > 50 else Xtr)

        pt = self.type_clf.predict(Xte)
        rule = np.array([TYPE_CLASSES.index(r) for r in self._rule_types(Xte)])
        ps = self.sev_clf.predict(Xte[yt_te > 0])
        self.metrics = {
            "n_train": int(len(Xtr)), "n_test": int(len(Xte)),
            "type_accuracy": round(float(accuracy_score(yt_te, pt)), 4),
            "type_macro_f1": round(float(f1_score(yt_te, pt, average="macro")), 4),
            "rule_baseline_accuracy": round(float(accuracy_score(yt_te, rule)), 4),
            "severity_accuracy": round(float(accuracy_score(ys_te[yt_te > 0], ps)), 4),
            # detection view: event (any type) vs noise
            "detection_precision": round(float(precision_score(yt_te > 0, pt > 0)), 4),
            "detection_recall": round(float(recall_score(yt_te > 0, pt > 0)), 4),
            "false_alarm_rate": round(float(((pt > 0) & (yt_te == 0)).sum() / max((yt_te == 0).sum(), 1)), 4),
            "split": "event-based hold-out (25% of simulated scenarios)",
            "type_report": classification_report(yt_te, pt, labels=list(range(len(TYPE_CLASSES))),
                                                 target_names=TYPE_CLASSES, output_dict=True, zero_division=0),
            "backend": "xgboost" if XGBClassifier is not None else "sklearn-hgb",
        }
        if verbose:
            print(json.dumps({k: v for k, v in self.metrics.items() if k != "type_report"}, indent=2))
        return self

    def fit_trajectory(self, X, Y):
        self.traj_x = GradientBoostingRegressor(n_estimators=200, max_depth=3, random_state=0).fit(X, Y[:, 0])
        self.traj_y = GradientBoostingRegressor(n_estimators=200, max_depth=3, random_state=0).fit(X, Y[:, 1])
        return self

    @staticmethod
    def _rule_types(X):
        out = []
        idx = {n: i for i, n in enumerate(FEATURE_NAMES)}
        for row in X:
            o = AnomalyObject(0, 0, 0, 0, 0, 0, 0, 0, {}, {}, {
                "precip": row[idx["zp_precip"]], "t2m": row[idx["zp_t2m"]],
                "wind": row[idx["zp_wind"]], "mslp": row[idx["zp_mslp"]]}, 0, 0)
            out.append(rule_based_type(o))
        return out

    # ---- inference
    @property
    def ready(self) -> bool:
        return self.type_clf is not None

    def annotate(self, objects: list[AnomalyObject]) -> list[AnomalyObject]:
        if not objects:
            return objects
        X = np.asarray([o.feature_vector() for o in objects], dtype=np.float32)
        if self.ready:
            tp = self.type_clf.predict_proba(X)
            sp = self.sev_clf.predict_proba(X)
            iso = -self.iso.score_samples(X)          # higher = more anomalous
            iso = (iso - 0.35) / 0.4                  # rough 0-1 scaling
        for i, o in enumerate(objects):
            _, score = severity_from_z(o)
            o.severity_score = round(score, 2)
            if self.ready:
                o.type_proba = {c: round(float(p), 3) for c, p in zip(TYPE_CLASSES, tp[i])}
                o.type = TYPE_CLASSES[int(np.argmax(tp[i]))]
                o.severity = SEV_CLASSES[int(np.argmax(sp[i]))]
                o.anomaly_score = round(float(np.clip(iso[i], 0, 1)), 3)
            else:
                o.type = rule_based_type(o)
                o.severity, _ = severity_from_z(o)
                o.anomaly_score = round(float(min(score / 8, 1)), 3)
        return objects

    def predict_next(self, hist_disp: list[tuple[float, float]], lat: float, lon: float) -> tuple[float, float]:
        """Next 6-hour displacement (km east, km north)."""
        if self.traj_x is None or len(hist_disp) < 3:
            dx = float(np.mean([d[0] for d in hist_disp])) if hist_disp else 0.0
            dy = float(np.mean([d[1] for d in hist_disp])) if hist_disp else 0.0
            return dx, dy
        h = hist_disp[-3:]
        x = np.array([[h[0][0], h[1][0], h[2][0], h[0][1], h[1][1], h[2][1], lat, lon]])
        return float(self.traj_x.predict(x)[0]), float(self.traj_y.predict(x)[0])

    # ---- persistence
    def save(self, path: Path | None = None):
        path = Path(path or settings.model_dir / "weatherpulse_models.joblib")
        path.parent.mkdir(parents=True, exist_ok=True)
        self.trained_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        joblib.dump(self.__dict__, path)
        (path.parent / "metrics.json").write_text(json.dumps(
            {"trained_at": self.trained_at, **{k: v for k, v in self.metrics.items()}}, indent=2))
        return path

    @classmethod
    def load(cls, path: Path | None = None) -> "ModelBundle":
        path = Path(path or settings.model_dir / "weatherpulse_models.joblib")
        mb = cls()
        if path.exists():
            try:
                mb.__dict__.update(joblib.load(path))
            except Exception as e:  # e.g. saved with a different scikit-learn version
                import logging
                logging.getLogger("weatherpulse.models").warning("Could not load %s (%s); retrain needed", path, e)
                mb = cls()
        return mb


def train_all(n_scenarios: int = 24, extra_X=None, extra_yt=None, extra_ys=None, verbose=True) -> ModelBundle:
    if verbose:
        print("Building labelled synthetic hindcasts ...")
    X, yt, ys, meta = build_training_set(n_scenarios=n_scenarios, verbose=verbose)
    groups = np.array([m["scenario"] for m in meta])
    if extra_X is not None and len(extra_X):
        X = np.vstack([X, extra_X])
        yt = np.concatenate([yt, extra_yt])
        ys = np.concatenate([ys, extra_ys])
        groups = np.concatenate([groups, np.full(len(extra_X), 10_000)])  # field feedback = own group
    mb = ModelBundle().fit(X, yt, ys, groups=groups, verbose=verbose)
    Xt, Yt = build_trajectory_set()
    mb.fit_trajectory(Xt, Yt)
    return mb
