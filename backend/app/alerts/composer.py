"""Alert drafting (Model 5 of the plan).

Structured facts -> role-specific message. Gemini writes the wording when a
key is configured; every number in its output is checked against the facts
and the draft falls back to a template if it contains an unverified number.
Safety advice comes from a fixed, approved list, never from the model.
"""
from __future__ import annotations

import re

from app.alerts import gemini

EVENT_NAME = {
    "heavy_rainfall": "Very heavy rainfall",
    "heatwave": "Heatwave",
    "cyclone": "Cyclonic storm",
    "coldwave": "Cold wave",
}

# Approved guidance (general NDMA / IMD public advice), by event type and role.
GUIDANCE = {
    "heavy_rainfall": {
        "citizen": ["Avoid underpasses, low-lying roads and drains", "Keep phones charged and a torch, water and medicines ready",
                    "Move valuables and electrical items off the floor", "Do not walk or drive through flowing water"],
        "school": ["Plan early dismissal before the rain window", "Keep students away from low-lying gates and basements",
                   "Check school bus routes avoid flood-prone underpasses", "Confirm parent contact lists"],
        "hospital": ["Test backup power and move critical stock above ground level", "Prepare for a rise in trauma and water-borne cases",
                     "Confirm ambulance routes that avoid waterlogging"],
        "rescue": ["Pre-position boats and dewatering pumps near known flood spots", "Keep teams on standby for the full rain window"],
        "traveller": ["Take the suggested safer route", "Do not enter waterlogged underpasses", "If caught in heavy rain, stop at a safe, raised place"],
    },
    "cyclone": {
        "citizen": ["Follow evacuation orders from local authorities", "Secure loose objects and stay indoors during the storm",
                    "Keep a radio, torch, water and dry food ready", "Stay away from the coast and fishing activity"],
        "school": ["Suspend classes during the warning window", "Prepare the building as a relief shelter if designated"],
        "hospital": ["Activate the disaster plan and backup power", "Shift patients away from windows on upper floors"],
        "rescue": ["Deploy to coastal blocks before landfall", "Coordinate evacuation of low-lying villages"],
        "traveller": ["Avoid coastal highways", "Postpone travel through the affected districts"],
    },
    "heatwave": {
        "citizen": ["Avoid going out between 12 noon and 4 pm", "Drink water often, even if not thirsty",
                    "Check on elderly people and children", "Wear light, loose cotton clothes"],
        "school": ["Shift outdoor activities to early morning", "Ensure drinking water and ORS are available"],
        "hospital": ["Prepare heat-stroke treatment areas and ORS stock", "Watch for heat illness in elderly patients"],
        "rescue": ["Keep cooling and hydration kits on vehicles"],
        "traveller": ["Carry water; avoid travel in the afternoon heat", "Do not leave children or pets in parked vehicles"],
    },
    "coldwave": {
        "citizen": ["Wear layered warm clothing", "Do not use coal or wood heaters in closed rooms",
                    "Check on elderly and homeless people"],
        "school": ["Consider later start times", "Keep classrooms ventilated if heaters are used"],
        "hospital": ["Prepare for hypothermia and respiratory cases"],
        "rescue": ["Support night shelters and blanket distribution"],
        "traveller": ["Expect fog; drive slowly with low-beam lights"],
    },
}

ROLE_AUDIENCE = {
    "official": "district officials and the emergency operations centre",
    "school": "school and college principals",
    "hospital": "hospital administrators",
    "rescue": "rescue team commanders",
    "citizen": "residents inside the risk zone (SMS / app push)",
    "traveller": "drivers and passengers heading toward the zone",
}

DISCLAIMER = "Prototype alert from a synthetic forecast scenario; follow official IMD / SDMA warnings."


def _fmt_int(n) -> str:
    """Indian digit grouping: 1234567 -> 12,34,567."""
    s = str(int(round(n)))
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    head = re.sub(r"(\d)(?=(\d{2})+$)", r"\1,", head)
    return f"{head},{tail}"


def facts_for(event: dict, role: str, point: dict | None = None) -> dict:
    p = point or event["peak"]
    imp = p.get("impact", {})
    pop = imp.get("population", {})
    return {
        "event_id": event["id"], "event": EVENT_NAME.get(event["type"], event["type"]),
        "severity": event["severity"], "place": event.get("place", ""),
        "window_start": event["window"]["start_local"], "window_end": event["window"]["end_local"],
        "direction": event["motion"]["direction"], "speed_kmh": round(event["motion"]["speed_kmh"]),
        "probability_pct": round(event["probability"] * 100),
        "people_total": pop.get("total", 0), "people_high": pop.get("high", 0),
        "schools": imp.get("counts", {}).get("school", 0), "hospitals": imp.get("counts", {}).get("hospital", 0),
        "vehicles": imp.get("counts", {}).get("vehicles_toward", 0),
        "guidance": GUIDANCE.get(event["type"], {}).get(role, GUIDANCE.get(event["type"], {}).get("citizen", [])),
        "audience": ROLE_AUDIENCE.get(role, role),
    }


def template(f: dict, role: str) -> tuple[str, str]:
    ev, sev, place = f["event"], f["severity"], f["place"]
    when = f"{f['window_start']} to {f['window_end']}"
    steps = "; ".join(f["guidance"][:3])
    if role == "official":
        title = f"{sev} risk: {ev.lower()} near {place}"
        body = (f"{ev} anomaly {f['event_id']} forecast near {place}, {when}. Moving {f['direction']} at about "
                f"{f['speed_kmh']} km/h; {f['probability_pct']}% of forecast scenarios agree. Estimated {_fmt_int(f['people_total'])} "
                f"residents within 8 km ({_fmt_int(f['people_high'])} in the high-risk ring), {f['schools']} schools/colleges and "
                f"{f['hospitals']} hospitals exposed; {f['vehicles']} vehicles heading toward the zone. Review and approve alerts.")
    elif role == "school":
        title = f"{sev} risk at your institution: {ev.lower()}"
        body = f"{ev} is forecast near your campus ({place}), {when}. {steps}."
    elif role == "hospital":
        title = f"{sev} risk: prepare for {ev.lower()}"
        body = f"{ev} is forecast near your facility ({place}), {when}. {steps}."
    elif role == "rescue":
        title = f"Pre-position order: {ev.lower()} near {place}"
        body = (f"{ev} forecast near {place}, {when}, moving {f['direction']}. About {_fmt_int(f['people_high'])} people "
                f"in the high-risk ring. {steps}.")
    elif role == "traveller":
        title = f"Risk zone ahead: {ev.lower()}"
        body = f"You are heading toward a {sev.lower()}-risk {ev.lower()} zone near {place} ({when}). {steps}."
    else:
        title = f"{sev} risk near you: {ev.lower()}"
        body = f"{ev} likely in your area ({place}), {when}. {steps}. Helpline 1070."
    return title, f"{body} {DISCLAIMER}"


_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _numbers_ok(text: str, f: dict) -> bool:
    allowed = set()
    for v in f.values():
        for n in _NUM.findall(str(v)):
            allowed.add(n.replace(",", ""))
    for k in ("people_total", "people_high"):
        allowed.add(_fmt_int(f[k]).replace(",", ""))
    allowed |= {"1070", "112", "1", "2", "3", "4", "5", "6", "7", "8", "0", "12", "24"}
    for n in _NUM.findall(text):
        if n.replace(",", "") not in allowed:
            return False
    return True


def draft(event: dict, role: str, language: str = "en", point: dict | None = None, use_ai: bool = True) -> dict:
    f = facts_for(event, role, point)
    title, body = template(f, role)
    source = "template"
    if use_ai and gemini.available():
        lang = {"en": "English", "kn": "Kannada", "hi": "Hindi", "ta": "Tamil", "te": "Telugu", "mr": "Marathi", "or": "Odia", "bn": "Bengali"}.get(language, "English")
        prompt = (
            f"Write a short, calm, actionable weather alert in {lang} for {f['audience']}.\n"
            f"Use ONLY these facts; do not add any number that is not in them:\n{f}\n"
            "Mention the time window, what is expected and 2-3 of the given guidance steps.\n"
            f"Citizen/traveller messages must be under 320 characters. End with: '{DISCLAIMER}'.\n"
            'Return JSON: {"title": "...", "body": "..."}'
        )
        out = gemini.json_of(gemini.generate([{"role": "user", "parts": [{"text": prompt}]}], json_mode=True))
        if isinstance(out, dict) and out.get("body"):
            if language != "en" or _numbers_ok(out["body"], f):
                title, body, source = out.get("title") or title, out["body"], f"gemini:{language}"
    return {"title": title, "body": body, "language": language, "generated_by": source, "facts": f}


def situation_summary(event: dict, use_ai: bool = True) -> dict:
    f = facts_for(event, "official")
    text = (f"{f['event']} anomaly forecast near {f['place']}, {f['window_start']} to {f['window_end']}, moving "
            f"{f['direction']} at about {f['speed_kmh']} km/h. Around {_fmt_int(f['people_total'])} residents, "
            f"{f['schools']} schools/colleges and {f['hospitals']} hospitals lie within 8 km of the peak.")
    source = "template"
    if use_ai and gemini.available():
        prompt = ("Write a 2-3 sentence situation summary for a district emergency officer. Use only these facts, "
                  f"no other numbers, plain language:\n{f}")
        out = gemini.text_of(gemini.generate([{"role": "user", "parts": [{"text": prompt}]}]))
        if out and _numbers_ok(out, f):
            text, source = out, "gemini"
    return {"text": text, "generated_by": source}
