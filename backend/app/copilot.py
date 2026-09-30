"""AI Copilot for officials: an LLM grounded on WeatherPulse data through tools.

We do NOT train a language model. Gemini is given function-calling access to
read-only tools over our datasets (events, Census 2011 population, institutions,
vehicles) and the map (geocoding, routing, highlights). It must answer from
tool results only; every tool call is returned to the UI and written to the
audit log. Without a GEMINI_API_KEY, a rule-based router calls the same tools
and composes the answer from their results, so the feature still works offline.
"""
from __future__ import annotations

import json
import math
import re

import httpx
import numpy as np

from app.alerts import gemini
from app.alerts.composer import EVENT_NAME, _fmt_int
from app.data.cities import CITIES
from app.data.population import PROJECTION_FACTOR, get_population
from app.geo import haversine_km, points_in_polygon

SYSTEM = """You are WeatherPulse Copilot, an assistant for Indian district emergency officials.
Rules:
- Answer ONLY from tool results. Never invent numbers, places, institutions or warnings.
- Always call tools to get facts; call several if needed.
- Population figures are Census 2011 estimates projected to the present; say "about" / "estimated".
- The forecast is a synthetic demo scenario and is not an official IMD warning; mention this when relevant.
- You can draft alerts (they go to a human approval queue) but you can never send them.
- Be concise: short paragraphs or a short list. Use Indian number formatting (lakh, crore) when natural.
- Reply in the user's language."""

TOOLS = [
    {"name": "list_events", "description": "List active anomaly events with severity, place, time window and people exposed.",
     "parameters": {"type": "OBJECT", "properties": {
         "severity": {"type": "STRING", "description": "High, Moderate or Low"},
         "type": {"type": "STRING", "description": "heavy_rainfall, cyclone, heatwave or coldwave"}}}},
    {"name": "get_event", "description": "Full details of one event: motion, probability, why it was flagged, window, impact counts.",
     "parameters": {"type": "OBJECT", "properties": {"event_id": {"type": "STRING"}}, "required": ["event_id"]}},
    {"name": "population_in_zone", "description": "Estimated residents in an event's risk rings (Census 2011, ward level in Bengaluru, district level elsewhere), with wards/districts.",
     "parameters": {"type": "OBJECT", "properties": {"event_id": {"type": "STRING"},
                                                    "lead_h": {"type": "INTEGER", "description": "forecast hour; omit for the highest-impact time"}},
                    "required": ["event_id"]}},
    {"name": "find_assets", "description": "Schools/colleges, hospitals or rescue teams inside an event's risk zone.",
     "parameters": {"type": "OBJECT", "properties": {"event_id": {"type": "STRING"},
                                                    "kind": {"type": "STRING", "description": "school, hospital or rescue_team"},
                                                    "ring": {"type": "STRING", "description": "high, moderate or low"}},
                    "required": ["event_id"]}},
    {"name": "vehicles_toward", "description": "Simulated vehicles inside or heading into an event's risk zone, with ETA.",
     "parameters": {"type": "OBJECT", "properties": {"event_id": {"type": "STRING"}, "kind": {"type": "STRING"}}, "required": ["event_id"]}},
    {"name": "district_population", "description": "Census 2011 population of an Indian district (and projected present estimate).",
     "parameters": {"type": "OBJECT", "properties": {"name": {"type": "STRING"}, "state": {"type": "STRING"}}, "required": ["name"]}},
    {"name": "ward_population", "description": "Census 2011 population of a Bengaluru (BBMP) ward by name or number.",
     "parameters": {"type": "OBJECT", "properties": {"name": {"type": "STRING"}}, "required": ["name"]}},
    {"name": "locate", "description": "Geocode a place name in India (city, BBMP ward or district) to coordinates.",
     "parameters": {"type": "OBJECT", "properties": {"place": {"type": "STRING"}}, "required": ["place"]}},
    {"name": "risk_at_location", "description": "Is a place/point inside any risk zone? Returns ring, event and distance.",
     "parameters": {"type": "OBJECT", "properties": {"place": {"type": "STRING"}, "lat": {"type": "NUMBER"}, "lon": {"type": "NUMBER"}}}},
    {"name": "route_eta", "description": "Driving distance/time between two points (OSRM if reachable, else straight-line estimate).",
     "parameters": {"type": "OBJECT", "properties": {"from_lat": {"type": "NUMBER"}, "from_lon": {"type": "NUMBER"},
                                                    "to_lat": {"type": "NUMBER"}, "to_lon": {"type": "NUMBER"}},
                    "required": ["from_lat", "from_lon", "to_lat", "to_lon"]}},
    {"name": "draft_alert", "description": "Create an alert DRAFT for human approval (cannot send).",
     "parameters": {"type": "OBJECT", "properties": {"event_id": {"type": "STRING"},
                                                    "role": {"type": "STRING", "description": "citizen, school, hospital, rescue, traveller, official"},
                                                    "language": {"type": "STRING", "description": "en, kn, hi, ta, te, mr, or, bn"}},
                    "required": ["event_id", "role"]}},
]


class Copilot:
    def __init__(self, pipeline):
        self.p = pipeline
        self.map: dict = {"events": [], "assets": [], "wards": [], "points": []}

    # ------------------------------------------------------------- tools
    def _ev(self, eid):
        ev = self.p.event(str(eid).strip().upper())
        if not ev:
            raise ValueError(f"Unknown event_id {eid}. Use list_events first.")
        return ev

    def list_events(self, severity=None, type=None):
        out = []
        for e in self.p.events():
            if severity and e["severity"].lower() != str(severity).lower():
                continue
            if type and e["type"] != type:
                continue
            out.append({"event_id": e["id"], "type": e["type"], "severity": e["severity"], "place": e["place"],
                        "window": f"{e['window']['start_local']} to {e['window']['end_local']}",
                        "people_within_8km": e["peak"]["impact"]["population"]["total"],
                        "probability": e["probability"]})
        self.map["events"] += [o["event_id"] for o in out]
        return {"events": out, "data_mode": "synthetic forecast scenario"}

    def get_event(self, event_id):
        e = self._ev(event_id)
        self.map["events"].append(e["id"])
        pk = e["peak"]
        return {"event_id": e["id"], "type": EVENT_NAME.get(e["type"], e["type"]), "severity": e["severity"],
                "place": e["place"], "window": e["window"], "motion": e["motion"], "probability": e["probability"],
                "why_flagged": e["why"]["text"], "uncertainty_km": pk["uncertainty_km"],
                "impact_counts": pk["impact"]["counts"], "people_within_8km": pk["impact"]["population"]["total"],
                "official_warning_linked": e["official_warning"], "data_source": e["data_source"]}

    def population_in_zone(self, event_id, lead_h=None):
        from app.pipeline.impact import population_by_ring
        e = self._ev(event_id)
        pt = self.p.point_at(e, int(lead_h)) if lead_h is not None else e["peak"]
        if pt is None:
            return {"event_id": e["id"], "note": f"Event not active at hour {lead_h}"}
        pop = pt["impact"]["population"] if "wards" in pt["impact"]["population"] else population_by_ring(pt["zone"])
        self.map["events"].append(e["id"])
        self.map["wards"] += [w["ward_no"] for w in pop.get("wards", [])[:40]]
        return {"event_id": e["id"], "valid_time": pt["valid_local"], "high_0_3km": pop["high"], "moderate_3_5km": pop["moderate"],
                "lower_5_8km": pop["low"], "total_0_8km": pop["total"], "households_est": pop.get("households"),
                "top_wards": [{"ward": w["ward_name"], "people": w["people"]} for w in pop.get("wards", [])[:8]],
                "districts": [{"district": d["district"], "state": d["state"], "people": d["people"]} for d in pop.get("districts", [])[:5]],
                "sources": pop.get("sources"), "method": pop.get("method"), "projection_factor_2011_to_now": PROJECTION_FACTOR}

    def find_assets(self, event_id, kind=None, ring=None):
        e = self._ev(event_id)
        items = e["peak"]["impact"].get("assets", [])
        if kind:
            k = {"schools": "school", "college": "school", "colleges": "school", "hospitals": "hospital",
                 "rescue": "rescue_team", "rescue_teams": "rescue_team"}.get(kind, kind)
            items = [a for a in items if a["kind"] == k]
        if ring:
            items = [a for a in items if a["ring"] == ring]
        self.map["assets"] += [a["id"] for a in items]
        self.map["events"].append(e["id"])
        return {"event_id": e["id"], "count": len(items), "data_source": "synthetic demo institutions",
                "items": [{"id": a["id"], "name": a["name"], "kind": a["kind"], "ring": a["ring"],
                           "distance_km": a["distance_km"], "capacity": a["capacity"]} for a in items[:25]]}

    def vehicles_toward(self, event_id, kind=None):
        e = self._ev(event_id)
        v = e.get("vehicles", {}).get("toward", [])
        if kind:
            v = [x for x in v if x["kind"] == kind]
        self.map["events"].append(e["id"])
        return {"event_id": e["id"], "count": len(v), "tracked": e.get("vehicles", {}).get("tracked", 0), "data_source": "simulated",
                "items": [{"id": x["id"], "kind": x["kind"], "status": x["status"], "eta_min": x["eta_min"],
                           "distance_km": x["distance_km"], "ring": x["ring"]} for x in v[:20]]}

    def district_population(self, name, state=None):
        rows = get_population().district_table(state=state, q=name, limit=5)
        return {"source": "Census of India 2011 (district), projected with factor " + str(PROJECTION_FACTOR),
                "matches": [{"district": r["district"], "state": r["state"], "population_2011": int(r["population_2011"]),
                             "estimated_now": int(r["population_now"]), "area_km2": r["area_km2"]} for r in rows]}

    def ward_population(self, name):
        pop = get_population()
        q = str(name).lower().strip()
        rows = [w for w in pop.wards if q in w["ward_name"].lower() or q == str(w["ward_no"])]
        self.map["wards"] += [w["ward_no"] for w in rows[:10]]
        return {"source": "Census of India 2011 · BBMP ward (DataMeet)",
                "matches": [{"ward_no": w["ward_no"], "ward": w["ward_name"], "population_2011": w["population_2011"],
                             "estimated_now": int(w["population_2011"] * PROJECTION_FACTOR), "area_km2": w["area_km2"]} for w in rows[:10]]}

    def locate(self, place):
        q = str(place).lower().strip()
        for name, state, lat, lon, *_ in CITIES:
            if q in name.lower() or name.lower() in q:
                self.map["points"].append([lon, lat])
                return {"place": f"{name}, {state}", "lat": lat, "lon": lon, "kind": "city"}
        pop = get_population()
        for w in pop.wards:
            if q in w["ward_name"].lower():
                ring = np.asarray(w["polys"][0])
                lon, lat = ring[:, 0].mean(), ring[:, 1].mean()
                self.map["wards"].append(w["ward_no"])
                return {"place": f"{w['ward_name']} (BBMP ward {w['ward_no']})", "lat": round(float(lat), 4), "lon": round(float(lon), 4), "kind": "ward"}
        d = pop.districts[pop.districts["district"].str.lower().str.contains(q, na=False)]
        if len(d):
            r = d.iloc[0]
            self.map["points"].append([float(r["lon"]), float(r["lat"])])
            return {"place": f"{r['district']} district, {r['state']}", "lat": float(r["lat"]), "lon": float(r["lon"]), "kind": "district centroid"}
        return {"error": f"Could not find '{place}'"}

    def risk_at_location(self, place=None, lat=None, lon=None):
        if place and (lat is None or lon is None):
            loc = self.locate(place)
            if "error" in loc:
                return loc
            lat, lon = loc["lat"], loc["lon"]
        lat, lon = float(lat), float(lon)
        hits, nearest = [], None
        for e in self.p.events():
            for q in e["track"]:
                for ring in ("high", "moderate", "low"):
                    if points_in_polygon(np.array([lon]), np.array([lat]), q["zone"]["rings"][ring])[0]:
                        hits.append({"event_id": e["id"], "ring": ring, "valid_time": q["valid_local"], "severity": q["severity"]})
                        break
            d = float(haversine_km(lat, lon, e["peak"]["lat"], e["peak"]["lon"]))
            if nearest is None or d < nearest["distance_km"]:
                nearest = {"event_id": e["id"], "distance_km": round(d, 1), "place": e["place"]}
        self.map["points"].append([lon, lat])
        return {"lat": lat, "lon": lon, "inside_zones": hits[:10], "nearest_event": nearest}

    def route_eta(self, from_lat, from_lon, to_lat, to_lon):
        try:
            r = httpx.get(f"https://router.project-osrm.org/route/v1/driving/{from_lon},{from_lat};{to_lon},{to_lat}",
                          params={"overview": "false"}, timeout=6)
            if r.status_code == 200 and r.json().get("routes"):
                rt = r.json()["routes"][0]
                return {"distance_km": round(rt["distance"] / 1000, 1), "duration_min": round(rt["duration"] / 60), "source": "OSRM (OpenStreetMap)"}
        except Exception:
            pass
        d = float(haversine_km(from_lat, from_lon, to_lat, to_lon)) * 1.35
        return {"distance_km": round(d, 1), "duration_min": round(d / 30 * 60), "source": "estimate: straight line x1.35 at 30 km/h (routing service unreachable)"}

    def draft_alert(self, event_id, role, language="en"):
        e = self._ev(event_id)
        a = self.p.draft_alert(e, role, language or "en", created_by="copilot")
        return {"alert_id": a["alert_id"], "status": a["approval_status"], "role": role, "language": a["language"],
                "title": a["title"], "message": a["message"], "note": "Draft placed in the approval queue; an official must approve it."}

    # ------------------------------------------------------------- runner
    def call(self, name, args):
        fn = getattr(self, name, None)
        if fn is None or name.startswith("_") or name not in {t["name"] for t in TOOLS}:
            return {"error": f"unknown tool {name}"}
        try:
            return fn(**(args or {}))
        except TypeError as e:
            return {"error": f"bad arguments: {e}"}
        except ValueError as e:
            return {"error": str(e)}

    def ask(self, question: str, history: list | None = None) -> dict:
        calls: list = []
        if gemini.available():
            out = self._ask_gemini(question, history or [], calls)
            if out:
                return self._finish(out, calls, "gemini")
            calls.clear()   # Gemini failed part-way: answer cleanly from the offline router instead
        res = self._finish(self._ask_offline(question, calls), calls, "offline-tools")
        st = gemini.status()
        if st["paused_for_s"]:
            res["note"] = (f"Gemini quota reached - answered with offline tools. "
                           f"AI answers resume in about {max(1, round(st['paused_for_s'] / 60))} min.")
        return res

    def _finish(self, text, calls, mode):
        m = {k: list(dict.fromkeys(v if k != "points" else [tuple(x) for x in v])) for k, v in self.map.items()}
        m["points"] = [list(x) for x in m["points"]]
        return {"answer": text, "tool_calls": calls, "map": m, "mode": mode}

    def _ask_gemini(self, question, history, calls) -> str | None:
        contents = []
        for h in history[-8:]:
            role = "model" if h.get("role") == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": str(h.get("content", ""))[:4000]}]})
        contents.append({"role": "user", "parts": [{"text": question}]})
        for _ in range(6):
            resp = gemini.generate(contents, system=SYSTEM, tools=TOOLS, temperature=0.1)
            parts = gemini.first_parts(resp)
            if not parts:
                return None
            fcs = [p["functionCall"] for p in parts if "functionCall" in p]
            if not fcs:
                return "".join(p.get("text", "") for p in parts).strip() or None
            contents.append({"role": "model", "parts": parts})
            responses = []
            for fc in fcs:
                result = self.call(fc["name"], fc.get("args", {}))
                calls.append({"name": fc["name"], "args": fc.get("args", {}), "result": _brief(result)})
                responses.append({"functionResponse": {"name": fc["name"], "response": {"result": json.loads(json.dumps(result, default=str))}}})
            contents.append({"role": "user", "parts": responses})
        return None

    # --- offline: simple intent routing over the same tools
    def _resolve_event(self, q):
        m = re.search(r"WX-[A-Z]{3}-\d{4}", q.upper())
        if m and self.p.event(m.group(0)):
            return self.p.event(m.group(0))
        ql = q.lower()
        for e in self.p.events():
            city = e["location"]["nearest_city"].lower()
            if city in ql or (e["location"].get("district") or "").lower() in ql:
                return e
        aliases = {"bangalore": "bengaluru", "bombay": "mumbai", "madras": "chennai", "orissa": "odisha", "cyclone": None}
        for k, v in aliases.items():
            if k in ql:
                for e in self.p.events():
                    if (v and v in e["place"].lower()) or (v is None and e["type"] == "cyclone"):
                        return e
        evs = self.p.events()
        return max(evs, key=lambda e: e["peak"]["impact"]["population"]["total"]) if evs else None

    def _run(self, calls, tool, **args):
        r = self.call(tool, args)
        calls.append({"name": tool, "args": args, "result": _brief(r)})
        return r

    def _ask_offline(self, q, calls) -> str:
        ql = q.lower()
        ev = self._resolve_event(q)
        if ev is None:
            return "There are no active anomaly events in the current forecast run."
        eid = ev["id"]
        parts = []
        if re.search(r"\b(list|all|active|which events|overview|summary|what.*happening)\b", ql):
            r = self._run(calls, "list_events")
            lines = [f"- {e['event_id']}: {e['severity']} {EVENT_NAME.get(e['type'], e['type']).lower()} near {e['place']}, "
                     f"{e['window']}; about {_fmt_int(e['people_within_8km'])} people within 8 km" for e in r["events"]]
            parts.append(f"{len(lines)} active anomalies in this run (synthetic scenario):\n" + "\n".join(lines))
        drafting = bool(re.search(r"draft|sms|message|write|notify", ql))
        admin_lookup = bool(re.search(r"\b(district|ward)\b", ql)) and not re.search(r"zone|ring|event|anomaly|risk", ql)
        if not admin_lookup and (re.search(r"(how many|population|residents|exposed|live)", ql) or (not drafting and re.search(r"citizens|people", ql))):
            r = self._run(calls, "population_in_zone", event_id=eid)
            txt = (f"For {eid} ({ev['place']}, {r['valid_time']}): about {_fmt_int(r['high_0_3km'])} people in the high-risk ring, "
                   f"{_fmt_int(r['moderate_3_5km'])} in the moderate ring and {_fmt_int(r['lower_5_8km'])} in the lower ring, "
                   f"{_fmt_int(r['total_0_8km'])} in total.")
            if r["top_wards"]:
                txt += " Most exposed wards: " + ", ".join(f"{w['ward']} ({_fmt_int(w['people'])})" for w in r["top_wards"][:4]) + "."
            txt += f" Source: {', '.join(r['sources'] or [])}, projected from 2011."
            parts.append(txt)
        kinds = [k for k, pat in (("hospital", r"hospital|medical|health"), ("school", r"school|college|institution|student"),
                                  ("rescue_team", r"rescue|ndrf|sdrf|fire")) if re.search(pat, ql)]
        for k in kinds:
            r = self._run(calls, "find_assets", event_id=eid, kind=k)
            label = {"hospital": "hospitals", "school": "schools/colleges", "rescue_team": "rescue units"}[k]
            if r["count"]:
                items = "; ".join(f"{a['name']} ({a['ring']}, {a['distance_km']} km)" for a in r["items"][:5])
                parts.append(f"{r['count']} {label} in the zone, closest-risk first: {items}.")
            else:
                parts.append(f"No {label} are inside the zone of {eid}.")
        if re.search(r"bus|vehicle|traffic|driver|car|truck|travell", ql) and not drafting:
            vk = next((k for k, pat in (("bus", r"\bbus"), ("truck", "truck"), ("car", r"\bcars?\b")) if re.search(pat, ql)), None)
            r = self._run(calls, "vehicles_toward", event_id=eid, **({"kind": vk} if vk else {}))
            items = "; ".join(f"{v['id']} ({v['kind']}, {v['status']}, ETA {v['eta_min']} min)" for v in r["items"][:5])
            parts.append(f"{r['count']} of {r['tracked']} simulated vehicles are inside or heading into the zone. {items}.")
        m = re.search(r"ward\s+(?:no\.?\s*)?([a-z0-9 ]+)", ql)
        if m:
            r = self._run(calls, "ward_population", name=m.group(1).strip().split(" ward")[0])
            if r["matches"]:
                w = r["matches"][0]
                parts.append(f"{w['ward']} (ward {w['ward_no']}): {_fmt_int(w['population_2011'])} in Census 2011, about {_fmt_int(w['estimated_now'])} today.")
        m = re.search(r"district\s+(?:of\s+)?([a-z ]+)|([a-z ]+)\s+district", ql)
        if m and "district" in ql:
            name = (m.group(1) or m.group(2) or "").strip().split(" ")[-1]
            r = self._run(calls, "district_population", name=name)
            if r["matches"]:
                d = r["matches"][0]
                parts.append(f"{d['district']} district ({d['state']}): {_fmt_int(d['population_2011'])} in Census 2011, about {_fmt_int(d['estimated_now'])} today.")
        if drafting or re.search(r"\balert\b", ql):
            lang = "kn" if re.search(r"kannada|ಕನ್ನಡ", ql) else "hi" if "hindi" in ql else "en"
            role = next((r for r, pat in (("school", "school|college"), ("hospital", "hospital"), ("rescue", "rescue"),
                                            ("traveller", "driver|bus|vehicle|travell"), ("official", "official|officer"))
                         if re.search(pat, ql)), "citizen")
            r = self._run(calls, "draft_alert", event_id=eid, role=role, language=lang)
            note = "" if lang == "en" else " (Translation needs a Gemini key; English text shown.)"
            parts.append(f"Draft {r['alert_id']} for {role}s is in the approval queue{note}:\n\"{r['message']}\"")
        if not parts:
            r = self._run(calls, "get_event", event_id=eid)
            c = r["impact_counts"]
            parts.append(f"{eid}: {r['severity']} {r['type'].lower()} near {r['place']}, {ev['window']['start_local']} to "
                         f"{ev['window']['end_local']}, moving {r['motion']['direction']} at about {round(r['motion']['speed_kmh'])} km/h "
                         f"({round(r['probability'] * 100)}% of forecast scenarios agree). About {_fmt_int(r['people_within_8km'])} people, "
                         f"{c['school']} schools/colleges and {c['hospital']} hospitals within 8 km. {r['why_flagged']}")
        parts.append("Note: synthetic forecast scenario; not an official IMD warning.")
        return "\n\n".join(parts)


def _brief(r, n=6):
    """Shorten tool results for the UI trace."""
    if isinstance(r, dict):
        out = {}
        for k, v in r.items():
            if isinstance(v, list):
                out[k] = v[:n] + ([f"... {len(v) - n} more"] if len(v) > n else [])
            else:
                out[k] = v
        return out
    return r
