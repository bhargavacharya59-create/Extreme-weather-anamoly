"""Minimal Gemini REST client (no SDK dependency).

Used for (a) alert/summary drafting and (b) the Copilot's function-calling
loop. The key stays server-side (GEMINI_API_KEY in backend/.env).
"""
from __future__ import annotations

import json
import logging

import httpx

from app.config import settings

log = logging.getLogger("weatherpulse.gemini")
BASE = "https://generativelanguage.googleapis.com/v1beta/models"


def enabled() -> bool:
    return bool(settings.gemini_api_key and settings.use_gemini)


def generate(contents: list, system: str | None = None, tools: list | None = None,
             temperature: float = 0.2, json_mode: bool = False, timeout: float = 25.0) -> dict | None:
    """Call models/{model}:generateContent. Returns the raw response JSON or None."""
    if not enabled():
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
