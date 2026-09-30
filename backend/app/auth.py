"""Demo authentication: signed bearer tokens (HMAC-SHA256, stdlib only) and
fictional role-based accounts. Replace with a proper identity provider for any
real deployment; never collect Aadhaar or other sensitive ID here.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time

SECRET = os.getenv("WP_AUTH_SECRET") or secrets.token_hex(32)
TOKEN_TTL_S = 12 * 3600

ROLES = ("official", "institution", "rescue", "citizen", "traveller")

# password for every demo account: demo123
_DEMO_HASH = hashlib.sha256(b"weatherpulse-demo:demo123").hexdigest()
DEMO_USERS = {
    "officer@demo.in": {"id": "U-OFF-1", "name": "R. Kumar", "role": "official",
                        "title": "District Emergency Officer", "org": "Bengaluru Urban DDMA"},
    "school@demo.in": {"id": "U-SCH-1", "name": "S. Rao", "role": "institution", "title": "Principal",
                       "org": "School (auto-assigned to the most exposed demo school)", "asset_kind": "school"},
    "hospital@demo.in": {"id": "U-HOS-1", "name": "Dr. A. Menon", "role": "institution", "title": "Medical Superintendent",
                         "org": "Hospital (auto-assigned to the most exposed demo hospital)", "asset_kind": "hospital"},
    "rescue@demo.in": {"id": "U-RES-1", "name": "Insp. P. Naik", "role": "rescue", "title": "Unit Commander", "org": "SDRF (demo)"},
    "citizen@demo.in": {"id": "U-CIT-1", "name": "Ananya", "role": "citizen", "title": "Resident", "org": "Bengaluru"},
    "driver@demo.in": {"id": "U-DRV-1", "name": "M. Gowda", "role": "traveller", "title": "Bus driver", "org": "Fleet (demo)"},
}


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def issue_token(email: str) -> str:
    u = DEMO_USERS[email]
    payload = {"sub": u["id"], "email": email, "role": u["role"], "exp": int(time.time()) + TOKEN_TTL_S}
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    sig = _b64(hmac.new(SECRET.encode(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def verify_token(token: str) -> dict | None:
    try:
        body, sig = token.split(".")
        good = _b64(hmac.new(SECRET.encode(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, good):
            return None
        payload = json.loads(_unb64(body))
        if payload["exp"] < time.time():
            return None
        return {**DEMO_USERS[payload["email"]], "email": payload["email"]}
    except Exception:
        return None


def login(email: str, password: str) -> dict | None:
    email = (email or "").strip().lower()
    if email not in DEMO_USERS:
        return None
    if not hmac.compare_digest(hashlib.sha256(f"weatherpulse-demo:{password}".encode()).hexdigest(), _DEMO_HASH):
        return None
    return {"token": issue_token(email), "user": {**DEMO_USERS[email], "email": email}}


def demo_accounts() -> list[dict]:
    return [{"email": e, "password": "demo123", **{k: u[k] for k in ("name", "role", "title")}} for e, u in DEMO_USERS.items()]
