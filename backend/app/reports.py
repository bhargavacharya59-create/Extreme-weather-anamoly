"""CSV and PDF exports (report_service)."""
from __future__ import annotations

import csv
import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.alerts.composer import EVENT_NAME, _fmt_int

INK = colors.HexColor("#14202B")
MUTED = colors.HexColor("#505B66")
SEV_COLOR = {"High": colors.HexColor("#B3261E"), "Moderate": colors.HexColor("#C26A00"), "Low": colors.HexColor("#8A7300")}


def events_csv(events: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["event_id", "type", "severity", "place", "window_start", "window_end", "direction", "speed_kmh",
                "probability", "peak_lat", "peak_lon", "people_high", "people_moderate", "people_low", "people_total",
                "schools", "hospitals", "rescue_units", "vehicles_toward", "data_source", "official_warning"])
    for e in events:
        pk = e["peak"]
        pop, c = pk["impact"]["population"], pk["impact"]["counts"]
        w.writerow([e["id"], e["type"], e["severity"], e["place"], e["window"]["start"], e["window"]["end"],
                    e["motion"]["direction"], e["motion"]["speed_kmh"], e["probability"], pk["lat"], pk["lon"],
                    pop["high"], pop["moderate"], pop["low"], pop["total"], c["school"], c["hospital"], c["rescue_team"],
                    c["vehicles_toward"], e["data_source"], e["official_warning"]])
    return buf.getvalue()


def _styles():
    ss = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle("h1", parent=ss["Heading1"], textColor=INK, fontSize=18, spaceAfter=4),
        "h2": ParagraphStyle("h2", parent=ss["Heading2"], textColor=INK, fontSize=12.5, spaceBefore=10, spaceAfter=4),
        "p": ParagraphStyle("p", parent=ss["BodyText"], fontSize=9.5, leading=13, textColor=INK),
        "small": ParagraphStyle("s", parent=ss["BodyText"], fontSize=8, leading=10, textColor=MUTED),
        "banner": ParagraphStyle("b", parent=ss["BodyText"], fontSize=8.5, leading=11, textColor=colors.HexColor("#5A3E00"),
                                 backColor=colors.HexColor("#FBE9C7"), borderPadding=5),
    }


_CELL = ParagraphStyle("cell", fontName="Helvetica", fontSize=8.5, leading=10.5, textColor=INK)


def _table(rows, widths, header=True):
    rows = [[Paragraph(str(c).replace("\n", "<br/>"), _CELL) if isinstance(c, str) and (len(c) > 40 or "\n" in c) else c
             for c in r] for r in rows]
    t = Table(rows, colWidths=widths)
    style = [("FONT", (0, 0), (-1, -1), "Helvetica", 8.5), ("TEXTCOLOR", (0, 0), (-1, -1), INK),
             ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#D9D7D0")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
    if header:
        style += [("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8.5), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F3F2EE"))]
    t.setStyle(TableStyle(style))
    return t


BANNER = ("DEMO DATA: synthetic forecast scenario. Population figures are Census 2011 estimates projected to the present; "
          "institutions and vehicles are simulated. This is not an official IMD warning.")


def event_pdf(e: dict, run: dict) -> bytes:
    st = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=14 * mm, bottomMargin=14 * mm,
                            title=f"WeatherPulse AI - {e['id']}")
    pk = e["peak"]
    pop, c = pk["impact"]["population"], pk["impact"]["counts"]
    story = [
        Paragraph("WeatherPulse AI · Event report", st["small"]),
        Paragraph(f"{EVENT_NAME.get(e['type'], e['type'])} anomaly · {e['id']}", st["h1"]),
        Paragraph(f"<font color='{SEV_COLOR[e['severity']].hexval()}'><b>{e['severity']} modelled risk</b></font> · {e['place']} · "
                  f"run {run['run_id']} issued {run['issue_time_local']}", st["p"]),
        Spacer(1, 5), Paragraph(BANNER, st["banner"]), Spacer(1, 6),
        Paragraph("Summary", st["h2"]), Paragraph(e["summary"]["text"], st["p"]),
        Paragraph("Forecast", st["h2"]),
        _table([
            ["Forecast window", f"{e['window']['start_local']} to {e['window']['end_local']}"],
            ["Movement", f"{e['motion']['direction']} at about {e['motion']['speed_kmh']} km/h"],
            ["Ensemble agreement", f"{round(e['probability'] * 100)}% of members exceed the threshold"],
            ["Path uncertainty", f"± {pk['uncertainty_km']} km (ensemble spread)"],
            ["Why flagged", e["why"]["text"]],
            ["Official warning linked", "No"],
        ], [45 * mm, 133 * mm], header=False),
        Paragraph("Exposure at highest-impact time (" + pk["valid_local"] + ")", st["h2"]),
        _table([["Ring", "Estimated residents"],
                ["High · 0–3 km", _fmt_int(pop["high"])], ["Moderate · 3–5 km", _fmt_int(pop["moderate"])],
                ["Lower · 5–8 km", _fmt_int(pop["low"])], ["Total", _fmt_int(pop["total"])]], [60 * mm, 50 * mm]),
        Spacer(1, 4),
        Paragraph(f"Method: {pop.get('method', '')}. Sources: {', '.join(pop.get('sources', []))}.", st["small"]),
        Paragraph("Institutions and transport", st["h2"]),
        _table([["Schools / colleges", c["school"]], ["Hospitals", c["hospital"]], ["Rescue units", c["rescue_team"]],
                ["Vehicles heading into zone (simulated)", c["vehicles_toward"]]], [80 * mm, 30 * mm], header=False),
    ]
    assets = pk["impact"].get("assets", [])
    if assets:
        story += [Paragraph("Exposed institutions", st["h2"]),
                  _table([["Name", "Type", "Ring", "Distance"]] +
                         [[a["name"], a["kind"].replace("_", " "), a["ring"], f"{a['distance_km']} km"] for a in assets[:30]],
                         [85 * mm, 30 * mm, 25 * mm, 25 * mm])]
    wards = pop.get("wards", [])
    if wards:
        story += [Paragraph("Most exposed wards (Census 2011, BBMP)", st["h2"]),
                  _table([["Ward", "Estimated residents in zone"]] + [[w["ward_name"], _fmt_int(w["people"])] for w in wards[:15]],
                         [100 * mm, 50 * mm])]
    story += [Paragraph("Track", st["h2"]),
              _table([["Valid time", "Lat", "Lon", "Severity", "Prob.", "People 0–8 km"]] +
                     [[q["valid_local"], q["lat"], q["lon"], q["severity"], f"{round(q['probability'] * 100)}%",
                       _fmt_int(q["impact"]["population"]["total"])] for q in e["track"]],
                     [48 * mm, 20 * mm, 20 * mm, 24 * mm, 18 * mm, 32 * mm])]
    doc.build(story)
    return buf.getvalue()


def run_pdf(run: dict, events: list[dict], alerts: list[dict]) -> bytes:
    st = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=14 * mm, bottomMargin=14 * mm,
                            title="WeatherPulse AI - situation report")
    s = run["summary"]
    story = [
        Paragraph("WeatherPulse AI · Situation report", st["small"]),
        Paragraph(f"Forecast run {run['run_id']}", st["h1"]),
        Paragraph(f"Issued {run['issue_time_local']} · {run['provider']} · {run['params']['members']} members · "
                  f"{run['params']['grid_res_deg']}° grid · lead time up to {run['params']['max_lead_h'] // 24} days", st["p"]),
        Spacer(1, 5), Paragraph(BANNER, st["banner"]),
        Paragraph("Overview", st["h2"]),
        _table([["Active anomalies", s["active"]], ["High / Moderate / Low",
                f"{s['by_severity']['High']} / {s['by_severity']['Moderate']} / {s['by_severity']['Low']}"],
                ["Residents within 8 km of event peaks", _fmt_int(s["population_exposed"])],
                ["Schools / hospitals exposed", f"{s['schools']} / {s['hospitals']}"],
                ["Vehicles heading into zones (simulated)", s["vehicles_toward"]]], [80 * mm, 60 * mm], header=False),
        Paragraph("Events", st["h2"]),
        _table([["Event", "Type", "Severity", "Place", "Window", "People"]] +
               [[e["id"], EVENT_NAME.get(e["type"], e["type"]), e["severity"], e["place"],
                 f"{e['window']['start_local']} →\n{e['window']['end_local']}", _fmt_int(e["peak"]["impact"]["population"]["total"])]
                for e in events], [26 * mm, 28 * mm, 18 * mm, 45 * mm, 42 * mm, 20 * mm]),
        Paragraph("Alerts", st["h2"]),
        _table([["Alert", "Event", "Audience", "Status", "Recipients"]] +
               [[a["alert_id"], a["event_id"], a["role"], a["approval_status"], _fmt_int(a["recipients"])] for a in alerts[:40]],
               [30 * mm, 30 * mm, 30 * mm, 25 * mm, 30 * mm]),
        Spacer(1, 6),
        Paragraph("Model: " + ", ".join(f"{k}={v}" for k, v in run.get("model_metrics", {}).items() if not isinstance(v, dict)), st["small"]),
    ]
    doc.build(story)
    return buf.getvalue()
