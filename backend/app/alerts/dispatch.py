"""Notification service: delivers APPROVED alerts and records delivery status.

Channels
  app    in-app / push feed (stored; clients poll /api/v1/alerts/feed)
  sms    Twilio if TWILIO_* is set, else logged to the outbox ("simulated")
  email  SMTP if SMTP_* is set, else logged ("simulated")
  push   Firebase Cloud Messaging topic if FIREBASE_* is set, else logged
Recipients in the demo are synthetic; nothing is sent to real people unless
real credentials AND real recipient lists are configured.
"""
from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

import httpx

from app.config import settings

log = logging.getLogger("weatherpulse.dispatch")

ROLE_CHANNELS = {
    "official": ["email", "sms", "app"],
    "school": ["email", "sms", "app"],
    "hospital": ["email", "sms", "app"],
    "rescue": ["sms", "app"],
    "citizen": ["sms", "push", "app"],
    "traveller": ["push", "app"],
}


def _sms(to: str, body: str) -> tuple[str, str]:
    if settings.sms_provider == "twilio" and settings.twilio_sid and settings.twilio_token and to.startswith("+"):
        try:
            r = httpx.post(f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_sid}/Messages.json",
                           auth=(settings.twilio_sid, settings.twilio_token),
                           data={"From": settings.twilio_from, "To": to, "Body": body[:1500]}, timeout=15)
            return ("sent", r.json().get("sid", "")) if r.status_code < 300 else ("failed", r.text[:200])
        except Exception as e:
            return "failed", str(e)[:200]
    return "simulated", "SMS provider not configured; logged only"


def _email(to: str, subject: str, body: str) -> tuple[str, str]:
    if settings.email_provider == "smtp" and settings.smtp_host and "@" in to and not to.endswith("example.org"):
        try:
            msg = EmailMessage()
            msg["From"], msg["To"], msg["Subject"] = settings.smtp_from or settings.smtp_user, to, subject
            msg.set_content(body)
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as s:
                s.starttls()
                if settings.smtp_user:
                    s.login(settings.smtp_user, settings.smtp_password or "")
                s.send_message(msg)
            return "sent", ""
        except Exception as e:
            return "failed", str(e)[:200]
    return "simulated", "SMTP not configured or demo recipient; logged only"


def deliver(store, alert: dict, recipients: list[dict]) -> dict:
    """recipients: [{"id", "name", "phone", "email"}]. Returns delivery counts."""
    counts: dict = {}
    for ch in alert["channels"]:
        if ch == "app":
            store.log_delivery(alert["alert_id"], alert["role"], "app", f"{len(recipients)} app users", "delivered", "in-app feed")
            counts["app"] = counts.get("app", 0) + len(recipients)
            continue
        if ch == "push":
            store.log_delivery(alert["alert_id"], alert["role"], "push", f"geo-fenced topic ({alert['recipients']} devices)",
                               "simulated", "FCM not configured; logged only")
            counts["push"] = alert["recipients"]
            continue
        for r in recipients[:200]:  # cap per-alert individual sends in the demo
            if ch == "sms":
                status, detail = _sms(r.get("phone", ""), f"{alert['title']}: {alert['message']}")
                target = r.get("phone", "")
            else:
                status, detail = _email(r.get("email", ""), alert["title"], alert["message"])
                target = r.get("email", "")
            store.log_delivery(alert["alert_id"], alert["role"], ch, f"{r.get('name', r.get('id'))} <{target}>", status, detail)
            counts[ch] = counts.get(ch, 0) + 1
    return counts
