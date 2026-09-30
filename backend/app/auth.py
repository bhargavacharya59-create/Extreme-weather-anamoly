"""Authentication: signed bearer tokens (HMAC-SHA256, stdlib only) over the
accounts table (app/accounts.py). Replace with a government identity provider
for real deployment; never collect Aadhaar or other sensitive ID here.
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
ASSET_KIND = {"SCH": "school", "HOS": "hospital", "RES": "rescue_team"}


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def issue_token(user: dict) -> str:
    payload = {"sub": user["user_id"], "role": user["role"], "exp": int(time.time()) + TOKEN_TTL_S}
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    sig = _b64(hmac.new(SECRET.encode(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def _enrich(u: dict) -> dict:
    u = dict(u)
    u["id"] = u["user_id"]
    if u.get("asset_id"):
        u["asset_kind"] = ASSET_KIND.get(u["asset_id"].split("-")[1], "school")
    return u


def verify_token(token: str) -> dict | None:
    from app.accounts import get_accounts
    try:
        body, sig = token.split(".")
        good = _b64(hmac.new(SECRET.encode(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, good):
            return None
        payload = json.loads(_unb64(body))
        if payload["exp"] < time.time():
            return None
        u = get_accounts().get(payload["sub"])
        return _enrich(u) if u else None
    except Exception:
        return None


def login(username: str, password: str) -> dict | None:
    from app.accounts import get_accounts
    u = get_accounts().authenticate(username, password)
    if not u:
        return None
    return {"token": issue_token(u), "user": _enrich(u)}


def session_for(user: dict) -> dict:
    return {"token": issue_token(user), "user": _enrich(user)}
