"""Train the WeatherPulse models (Model 1 anomaly/type/severity + trajectory model).

    python -m scripts.train_models            # 30 simulated hindcast scenarios
    python -m scripts.train_models --scenarios 60

Training data are labelled synthetic hindcasts (every month of the year) plus any
field feedback stored through POST /api/v1/feedback. With real ERA5 / IMD data,
replace build_training_set() inputs with load_ensemble_forecast() +
load_reanalysis_climatology() and labels from documented IMD events.
Evaluation uses an event-based hold-out (whole scenarios), never random rows.
"""
import argparse
import json

from app.pipeline.models import train_all
from app.storage import Store


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", type=int, default=30)
    args = ap.parse_args()
    fb = Store().feedback()
    if fb:
        print(f"{len(fb)} field-feedback records stored (used for validation reports; see docs/MODELS.md)")
    mb = train_all(n_scenarios=args.scenarios, verbose=True)
    path = mb.save()
    print("\nSaved", path)
    print(json.dumps({k: v for k, v in mb.metrics.items() if k != "type_report"}, indent=2))


if __name__ == "__main__":
    main()
