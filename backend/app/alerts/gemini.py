"""Minimal Gemini REST client (no SDK dependency).

Used for (a) alert/summary drafting and (b) the Copilot's function-calling
loop. The key stays server-side (GEMINI_API_KEY in backend/.env).
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time

import httpx

from app.config import settings

log = logging.getLogger("weatherpulse.gemini")
BASE = "https://generativelanguage.googleapis.com/v1beta/models"


# Quota handling: after an HTTP 429 (free-tier limit) we stop calling Gemini for a while
# instead of hammering it; callers fall back to templates / the offline Copilot.
_lock = threading.Lock()
_paused_until = 0.0
_last_error: str | None = None
DEFAULT_PAUSE_S = 60.0
DAILY_PAUSE_S = 15 * 60.0


def enabled() -> bool:
    """Key configured and not switched off (ignores a temporary quota pause)."""
    return bool(settings.gemini_api_key and settings.use_gemini)


def available() -> bool:
    return enabled() and time.time() >= _paused_until


def status() -> dict:
    left = max(0, round(_paused_until - time.time()))
    return {"configured": enabled(), "model": settings.gemini_model if enabled() else None,
            "paused_for_s": left, "last_error": _last_error if left else None}


def _pause_after_429(r: httpx.Response) -> float:
    """Seconds to back off: Retry-After header, the RetryInfo delay in the body, or a default."""
    wait = None
    try:
        wait = float(r.headers.get("retry-after"))
    except (TypeError, ValueError):
        pass
    if wait is None:
        m = re.search(r'"retryDelay":\s*"(\d+(?:\.\d+)?)s"', r.text)
        if m:
            wait = float(m.group(1))
    if wait is None:
        # "PerDay" quota ids mean the daily allowance is gone: back off longer.
        wait = DAILY_PAUSE_S if "PerDay" in r.text else DEFAULT_PAUSE_S
    return min(max(wait, 10.0), 3600.0)


def generate(contents: list, system: str | None = None, tools: list | None = None,
             temperature: float = 0.2, json_mode: bool = False, timeout: float = 25.0) -> dict | None:
    """Call models/{model}:generateContent. Returns the raw response JSON or None."""
    global _paused_until, _last_error
    if not available():
        return None
    body: dict = {"contents": contents, "generationConfig": {"temperature": temperature}}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    if tools:
        body["tools"] = [{"functionDeclarations": tools}]
    if json_mode:
        body["generationConfig"]["responseMimeType"] = "application/json"
    try:
        r = httpx.post(f"{BASE}/{settings.gemini_model}:generateContent",
                       headers={"x-goog-api-key": settings.gemini_api_key, "Content-Type": "application/json"},
                       json=body, timeout=timeout)
        if r.status_code == 429:
            wait = _pause_after_429(r)
            with _lock:
                first = time.time() >= _paused_until
                _paused_until = max(_paused_until, time.time() + wait)
                _last_error = "quota exceeded (HTTP 429)"
            if first:
                log.warning("Gemini quota exceeded (HTTP 429) - pausing Gemini for %ds and using templates / "
                            "offline Copilot meanwhile. Tip: GEMINI_MODEL=gemini-2.5-flash-lite has higher free limits.",
                            wait)
            return None
        if r.status_code != 200:
            log.warning("Gemini HTTP %s: %s", r.status_code, r.text[:300])
            return None
        return r.json()
    except Exception as e:  # network, timeout, JSON
        log.warning("Gemini call failed: %s", e)
        return None


def first_parts(resp: dict | None) -> list:
    try:
        return resp["candidates"][0]["content"]["parts"]
    except Exception:
        return []


def text_of(resp: dict | None) -> str | None:
    parts = first_parts(resp)
    txt = "".join(p.get("text", "") for p in parts if "text" in p).strip()
    return txt or None


def json_of(resp: dict | None):
    txt = text_of(resp)
    if not txt:
        return None
    txt = txt.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        return None
