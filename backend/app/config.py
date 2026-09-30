"""Runtime configuration, read from environment variables (see .env.example)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent


def _env_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("WP_DATA_DIR", REPO_DIR / "data")))
    db_path: Path = field(default_factory=lambda: Path(os.getenv("WP_DB_PATH", REPO_DIR / "data" / "weatherpulse.db")))
    model_dir: Path = field(default_factory=lambda: Path(os.getenv("WP_MODEL_DIR", REPO_DIR / "data" / "models")))

    # Forecast grid (India domain). 0.25 deg ~ 27 km, same as ERA5.
    lat_min: float = float(os.getenv("WP_LAT_MIN", 6.0))
    lat_max: float = float(os.getenv("WP_LAT_MAX", 37.0))
    lon_min: float = float(os.getenv("WP_LON_MIN", 68.0))
    lon_max: float = float(os.getenv("WP_LON_MAX", 98.0))
    grid_res: float = float(os.getenv("WP_GRID_RES", 0.25))
    step_hours: int = int(os.getenv("WP_STEP_HOURS", 6))
    max_lead_hours: int = int(os.getenv("WP_MAX_LEAD_HOURS", 240))  # 10 days
    ensemble_members: int = int(os.getenv("WP_ENSEMBLE_MEMBERS", 6))

    # Detection thresholds (standardised anomaly, sigma units)
    z_threshold: float = float(os.getenv("WP_Z_THRESHOLD", 2.5))
    min_object_cells: int = int(os.getenv("WP_MIN_OBJECT_CELLS", 3))

    # Impact-zone base radii in km (high / moderate / low) - adapted per event
    ring_radii_km: tuple = (3.0, 5.0, 8.0)

    # Gemini (optional). Without a key, template messages are used.
    gemini_api_key: str | None = field(default_factory=lambda: os.getenv("GEMINI_API_KEY") or None)
    gemini_model: str = field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))
    use_gemini: bool = field(default_factory=lambda: _env_bool("WP_USE_GEMINI", True))

    # Alert channels. "log" writes to the outbox table; twilio/smtp need credentials.
    sms_provider: str = field(default_factory=lambda: os.getenv("WP_SMS_PROVIDER", "log"))
    email_provider: str = field(default_factory=lambda: os.getenv("WP_EMAIL_PROVIDER", "log"))
    twilio_sid: str | None = field(default_factory=lambda: os.getenv("TWILIO_ACCOUNT_SID"))
    twilio_token: str | None = field(default_factory=lambda: os.getenv("TWILIO_AUTH_TOKEN"))
    twilio_from: str | None = field(default_factory=lambda: os.getenv("TWILIO_FROM_NUMBER"))
    smtp_host: str | None = field(default_factory=lambda: os.getenv("SMTP_HOST"))
    smtp_port: int = field(default_factory=lambda: int(os.getenv("SMTP_PORT", 587)))
    smtp_user: str | None = field(default_factory=lambda: os.getenv("SMTP_USER"))
    smtp_password: str | None = field(default_factory=lambda: os.getenv("SMTP_PASSWORD"))
    smtp_from: str | None = field(default_factory=lambda: os.getenv("SMTP_FROM"))

    cors_origins: list = field(
        default_factory=lambda: [o.strip() for o in os.getenv("WP_CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]
    )
    run_on_startup: bool = field(default_factory=lambda: _env_bool("WP_RUN_ON_STARTUP", True))
    default_seed: int = int(os.getenv("WP_SEED", 42))

    def ensure_dirs(self) -> None:
        for p in (self.data_dir, self.model_dir, self.db_path.parent):
            Path(p).mkdir(parents=True, exist_ok=True)


settings = Settings()
