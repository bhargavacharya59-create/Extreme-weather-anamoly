"""User accounts (demo dataset).

* Government official : one account.
* Institutions        : one account per school/college, hospital and rescue unit;
                        username = the institution's name.
* Drivers             : one account per simulated bus (username = bus number).
* Citizens            : self-registration (mobile number + password), plus two samples.

Demo passwords are derived deterministically from the username, so the Excel
sheet produced by `python -m scripts.export_accounts` matches the database on
any machine. Passwords are stored only as salted PBKDF2-SHA256 hashes.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import threading

from app.storage import Store, now_iso

PBKDF2_ROUNDS = 12_000
_WORDS = ["Monsoon", "Cyclone", "Thunder", "Rainbow", "Storm", "River", "Cloud", "Breeze", "Harbor", "Summit",
          "Falcon", "Lotus", "Tiger", "Coral", "Comet", "Canyon", "Meadow", "Orbit", "Nimbus", "Ocean"]
_lock = threading.Lock()

GOVT_USERNAME = "GovtOfficer"

KIND_ROLE = {"school": "institution", "hospital": "institution", "rescue_team": "rescue"}
KIND_TITLE = {"school": "Principal", "hospital": "Medical Superintendent", "rescue_team": "Unit Commander"}


def norm(username: str) -> str:
    return re.sub(r"\s+", " ", (username or "").strip().lower())


def demo_password(key: str) -> str:
    """Deterministic, readable demo password, unique per account (e.g. Monsoon@4821)."""
    h = hashlib.sha256(f"weatherpulse-demo-v1:{key}".encode()).digest()
    return f"{_WORDS[h[0] % len(_WORDS)]}@{int.from_bytes(h[1:4], 'big') % 9000 + 1000}"


def hash_password(pw: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(12)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, PBKDF2_ROUNDS)
    return f"{salt.hex()}${dk.hex()}"


def check_password(pw: str, stored: str) -> bool:
    try:
        salt, dk = stored.split("$")
        got = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), PBKDF2_ROUNDS).hex()
        return hmac.compare_digest(got, dk)
    except Exception:
        return False


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  user_id TEXT PRIMARY KEY, username TEXT, username_norm TEXT UNIQUE, password_hash TEXT,
  role TEXT, name TEXT, title TEXT, org TEXT, asset_id TEXT, vehicle_id TEXT,
  phone TEXT, email TEXT, home_lat REAL, home_lon REAL, home_label TEXT, created_at TEXT, source TEXT);
CREATE INDEX IF NOT EXISTS users_phone ON users(phone);
"""


class Accounts:
    def __init__(self, store: Store):
        self.store = store
        with _lock:
            store.conn.executescript(SCHEMA)
            store.conn.commit()

    # ------------------------------------------------------------ queries
    def get(self, user_id: str) -> dict | None:
        rows = self.store.query("SELECT * FROM users WHERE user_id=?", (user_id,))
        return self._public(rows[0]) if rows else None

    def find_login(self, login: str) -> dict | None:
        n = norm(login)
        digits = re.sub(r"\D", "", login or "")
        rows = self.store.query("SELECT * FROM users WHERE username_norm=?", (n,))
        if not rows and len(digits) >= 10:
            rows = self.store.query("SELECT * FROM users WHERE phone=? AND role='citizen'", (digits[-10:],))
        if not rows and "@" in n:
            rows = self.store.query("SELECT * FROM users WHERE lower(email)=?", (n,))
        return rows[0] if rows else None

    def authenticate(self, login: str, password: str) -> dict | None:
        row = self.find_login(login)
        if row and check_password(password or "", row["password_hash"]):
            return self._public(row)
        return None

    def directory(self, role: str | None = None, q: str = "", limit: int = 50) -> list[dict]:
        sql, p = "SELECT user_id, username, role, title, org, asset_id, vehicle_id FROM users WHERE role != 'citizen'", []
        if role:
            sql += " AND role=?"
            p.append(role)
        if q:
            sql += " AND username_norm LIKE ?"
            p.append(f"%{norm(q)}%")
        return self.store.query(sql + " ORDER BY username LIMIT ?", (*p, limit))

    def count(self, role=None, source=None) -> int:
        sql, p = "SELECT COUNT(*) AS n FROM users WHERE 1=1", []
        if role:
            sql, p = sql + " AND role=?", [*p, role]
        if source:
            sql, p = sql + " AND source=?", [*p, source]
        return self.store.query(sql, tuple(p))[0]["n"]

    @staticmethod
    def _public(row: dict) -> dict:
        return {k: v for k, v in row.items() if k not in ("password_hash", "username_norm")}

    # ------------------------------------------------------------ writes
    def _insert(self, u: dict, password: str):
        self.store.execute(
            "INSERT OR IGNORE INTO users (user_id, username, username_norm, password_hash, role, name, title, org, asset_id, "
            "vehicle_id, phone, email, home_lat, home_lon, home_label, created_at, source) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (u["user_id"], u["username"], norm(u["username"]), hash_password(password), u["role"], u.get("name"), u.get("title"),
             u.get("org"), u.get("asset_id"), u.get("vehicle_id"), u.get("phone"), u.get("email"), u.get("home_lat"),
             u.get("home_lon"), u.get("home_label"), now_iso(), u.get("source", "demo_seed")))

    def register_citizen(self, name: str, phone: str, password: str, email: str | None,
                         home_lat: float, home_lon: float, home_label: str) -> dict:
        digits = re.sub(r"\D", "", phone or "")[-10:]
        if len(digits) != 10:
            raise ValueError("Enter a 10-digit mobile number")
        if len(password or "") < 6:
            raise ValueError("Password must be at least 6 characters")
        if not (name or "").strip():
            raise ValueError("Enter your name")
        if self.store.query("SELECT 1 FROM users WHERE phone=? AND role='citizen'", (digits,)):
            raise ValueError("This mobile number is already registered. Please sign in.")
        uid = f"CIT-{secrets.token_hex(4).upper()}"
        self._insert({"user_id": uid, "username": f"citizen-{digits}", "role": "citizen", "name": name.strip(),
                      "title": "Resident", "org": home_label, "phone": digits, "email": (email or "").strip() or None,
                      "home_lat": home_lat, "home_lon": home_lon, "home_label": home_label, "source": "registered"}, password)
        return self.get(uid)

    # ------------------------------------------------------------ demo seed
    def seed_static(self, assets: list[dict]) -> int:
        """Government + institutions + rescue units + sample citizens (idempotent)."""
        before = self.count()
        self._insert({"user_id": "GOV-0001", "username": GOVT_USERNAME, "role": "official", "name": "Govt. Officer",
                      "title": "District Emergency Officer", "org": "District Disaster Management Authority"}, demo_password(GOVT_USERNAME))
        for a in assets:
            self._insert({"user_id": f"U-{a['id']}", "username": a["name"], "role": KIND_ROLE[a["kind"]],
                          "name": a["name"], "title": KIND_TITLE[a["kind"]], "org": a["name"], "asset_id": a["id"],
                          "email": a["contact"]}, demo_password(a["name"]))
        for i, (nm, ph, lat, lon, label) in enumerate([
            ("Ananya Rao", "9000000001", 12.9352, 77.6245, "Koramangala, Bengaluru"),
            ("Rahul Das", "9000000002", 20.2961, 85.8245, "Bhubaneswar, Odisha"),
        ]):
            self._insert({"user_id": f"CIT-DEMO-{i + 1}", "username": f"citizen-{ph}", "role": "citizen", "name": nm,
                          "title": "Resident", "org": label, "phone": ph, "home_lat": lat, "home_lon": lon,
                          "home_label": label}, demo_password(f"citizen-{ph}"))
        return self.count() - before

    def seed_drivers(self, events: list[dict]) -> int:
        """One driver account per simulated bus in the current forecast run (idempotent)."""
        before = self.count()
        for e in events:
            for v in e.get("vehicles", {}).get("all", []):
                if v["kind"] != "bus":
                    continue
                self._insert({"user_id": f"DRV-{v['id']}", "username": v["id"], "role": "traveller",
                              "name": f"Driver, {v['id']}", "title": "Bus driver", "org": v.get("operator", ""),
                              "vehicle_id": v["id"]}, demo_password(v["id"]))
        return self.count() - before


_acc: Accounts | None = None


def get_accounts() -> Accounts:
    global _acc
    if _acc is None:
        from app.service import get_pipeline
        p = get_pipeline()
        _acc = Accounts(p.store)
        if _acc.count(source="demo_seed") == 0 or not _acc.find_login(GOVT_USERNAME):
            _acc.seed_static(p.assets)
    return _acc
