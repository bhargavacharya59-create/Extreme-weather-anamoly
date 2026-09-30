"""Export the synthetic demo datasets to data/synthetic/ so they can be inspected,
shared or loaded into PostGIS.

    python -m scripts.generate_synthetic_data

Writes (all clearly labelled data_source=synthetic_demo):
  forecast_ensemble.npz     NEPS-like ensemble (member, lead, lat, lon) x 4 variables
  climatology_month09.npz   ERA5-like baseline mean/std
  truth_events.json         the injected ground-truth events
  institutions.geojson      fictional schools, hospitals, rescue units
  vehicles.geojson          simulated vehicle snapshot
  citizens_demo.csv         fictional opt-in app users (no real personal data)
  incident_reports.csv      fictional incident / response records
"""
import csv
import json

import numpy as np

from app.config import REPO_DIR
from app.data.cities import CITIES
from app.data.synthetic import (Grid, climatology, demo_scenario, generate_assets, generate_forecast,
                                generate_vehicles, random_events)
from app.geo import destination

OUT = REPO_DIR / "data" / "synthetic"

FIRST = ["Aarav", "Diya", "Kabir", "Meera", "Rohan", "Isha", "Arjun", "Saanvi", "Vihaan", "Anaya", "Kiran", "Nisha"]
LAST = ["Sharma", "Rao", "Iyer", "Das", "Patil", "Nair", "Singh", "Gowda", "Reddy", "Khan", "Bose", "Mehta"]


def main(seed: int = 42, month: int = 9):
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    g = Grid()
    truth = demo_scenario() + random_events(rng, 2, month, g, prefix="EV-X")
    b = generate_forecast(g, month, truth, seed=seed)
    np.savez_compressed(OUT / "forecast_ensemble.npz", lats=g.lats, lons=g.lons, lead_hours=b.lead_hours,
                        **{v: a.astype(np.float16) for v, a in b.fields.items()})
    clim = climatology(g, month)
    np.savez_compressed(OUT / f"climatology_month{month:02d}.npz",
                        **{f"{v}_mean": m for v, (m, s) in clim.items()}, **{f"{v}_std": s for v, (m, s) in clim.items()})
    (OUT / "truth_events.json").write_text(json.dumps([t.to_dict() for t in truth], indent=2))

    def fc(items):
        return {"type": "FeatureCollection", "features": [
            {"type": "Feature", "geometry": {"type": "Point", "coordinates": [i["lon"], i["lat"]]},
             "properties": {**i, "data_source": "synthetic_demo"}} for i in items]}
    (OUT / "institutions.geojson").write_text(json.dumps(fc(generate_assets())))
    (OUT / "vehicles.geojson").write_text(json.dumps(fc(generate_vehicles())))

    with open(OUT / "citizens_demo.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["user_id", "name", "phone", "email", "city", "lat", "lon", "language", "opt_in_alerts", "data_source"])
        for i in range(500):
            c = CITIES[int(rng.integers(len(CITIES)))]
            la, lo = destination(c[2], c[3], float(rng.uniform(0, 360)), float(abs(rng.normal(0, c[5]))))
            name = f"{FIRST[int(rng.integers(len(FIRST)))]} {LAST[int(rng.integers(len(LAST)))]}"
            w.writerow([f"CIT-{i:05d}", name, f"+91-00000-{i:05d}", f"user{i:05d}@example.org", c[0], round(la, 5), round(lo, 5),
                        str(rng.choice(["en", "kn", "hi", "ta", "te"])), True, "synthetic_demo"])
    with open(OUT / "incident_reports.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["report_id", "date", "city", "type", "summary", "assigned_officer", "response_min", "status", "data_source"])
        kinds = [("waterlogging", "Underpass waterlogged, traffic diverted"), ("tree_fall", "Tree fall blocking road"),
                 ("power_outage", "Feeder outage after heavy rain"), ("heat_illness", "Heat exhaustion cases at bus stand")]
        for i in range(120):
            k, s = kinds[int(rng.integers(len(kinds)))]
            w.writerow([f"INC-{i:04d}", f"2025-{int(rng.integers(6, 11)):02d}-{int(rng.integers(1, 29)):02d}",
                        CITIES[int(rng.integers(len(CITIES)))][0], k, s, f"Officer {chr(65 + i % 26)}. (fictional)",
                        int(rng.integers(12, 180)), str(rng.choice(["closed", "closed", "pending"])), "synthetic_demo"])
    print("written to", OUT)
    for p in sorted(OUT.iterdir()):
        print(f"  {p.name:28s} {p.stat().st_size / 1e6:6.2f} MB")


if __name__ == "__main__":
    main()
