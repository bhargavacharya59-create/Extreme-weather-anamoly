"""FastAPI entry point:  uvicorn app.main:app --reload --port 8000"""
from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from app.config import settings  # loads backend/.env

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from app import __version__  # noqa: E402
from app.api.routes import router  # noqa: E402
from app.service import get_pipeline  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("weatherpulse")


def _bootstrap():
    """First start: train the models if none are saved (about a minute), then run the pipeline."""
    p = get_pipeline()
    from app.accounts import get_accounts
    get_accounts()          # creates the demo login accounts on first start (a few seconds)
    if not p.models.ready:
        log.info("No trained models in %s - training now (first start only, ~1 min)...", settings.model_dir)
        p.status = "training"
        from app.pipeline.models import ModelBundle, train_all
        train_all(n_scenarios=24, verbose=False).save()
        p.models = ModelBundle.load()
    p.run()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.run_on_startup:
        threading.Thread(target=_bootstrap, daemon=True).start()
    yield


app = FastAPI(title="WeatherPulse AI", version=__version__,
              description="AI-driven spatio-temporal tracking of extreme weather anomalies (SIH26078).", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(router)


@app.get("/")
def root():
    return {"name": "WeatherPulse AI", "version": __version__, "docs": "/docs", "api": "/api/v1"}
