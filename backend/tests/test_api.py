"""API tests with FastAPI's TestClient (skipped if FastAPI is not installed)."""
import os
import unittest

os.environ.setdefault("WP_RUN_ON_STARTUP", "0")

try:
    from fastapi.testclient import TestClient
    HAVE_FASTAPI = True
except Exception:  # pragma: no cover
    HAVE_FASTAPI = False


@unittest.skipUnless(HAVE_FASTAPI, "fastapi not installed")
class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app.main import app
        from app.service import get_pipeline
        get_pipeline().run()
        cls.c = TestClient(app)
        from app.accounts import GOVT_USERNAME, demo_password
        tok = cls.c.post("/api/v1/auth/login", json={"username": GOVT_USERNAME, "password": demo_password(GOVT_USERNAME)}).json()["token"]
        cls.h = {"Authorization": f"Bearer {tok}"}
        tok2 = cls.c.post("/api/v1/auth/login", json={"username": "9000000001", "password": demo_password("citizen-9000000001")}).json()["token"]
        cls.hc = {"Authorization": f"Bearer {tok2}"}

    def test_auth_required(self):
        self.assertEqual(self.c.get("/api/v1/anomalies").status_code, 401)

    def test_role_guard(self):
        self.assertEqual(self.c.get("/api/v1/alerts", headers=self.hc).status_code, 403)

    def test_dashboard_and_anomalies(self):
        s = self.c.get("/api/v1/dashboard/summary", headers=self.h).json()
        self.assertGreater(s["active"], 0)
        evs = self.c.get("/api/v1/anomalies", headers=self.h).json()
        eid = evs[0]["id"]
        for path in (f"/api/v1/anomalies/{eid}", f"/api/v1/anomalies/{eid}/trajectory", f"/api/v1/anomalies/{eid}/impact",
                     "/api/v1/maps/risk-zones", "/api/v1/maps/tracks", "/api/v1/vehicles", "/api/v1/analytics"):
            self.assertEqual(self.c.get(path, headers=self.h).status_code, 200, path)

    def test_alert_workflow(self):
        eid = self.c.get("/api/v1/anomalies", headers=self.h).json()[0]["id"]
        a = self.c.post("/api/v1/alerts/draft", headers=self.h, json={"event_id": eid, "role": "citizen"}).json()
        self.assertEqual(a["approval_status"], "draft")
        r = self.c.post(f"/api/v1/alerts/{a['alert_id']}/approve", headers=self.h).json()
        self.assertEqual(r["alert"]["approval_status"], "sent")
        self.assertTrue(r["deliveries"])

    def test_register_and_wrong_password(self):
        r = self.c.post("/api/v1/auth/register", json={"name": "Test User", "phone": "9123456780", "password": "secret1", "locality_id": "C-Bengaluru"})
        self.assertIn(r.status_code, (200, 400))  # 400 if already registered by an earlier run
        self.assertEqual(self.c.post("/api/v1/auth/login", json={"username": "9123456780", "password": "nope"}).status_code, 401)
        self.assertEqual(self.c.post("/api/v1/auth/login", json={"username": "9123456780", "password": "secret1"}).status_code, 200)

    def test_copilot_grounded(self):
        r = self.c.post("/api/v1/copilot/ask", headers=self.h, json={"question": "How many people are in the Bengaluru zone?"}).json()
        self.assertTrue(r["tool_calls"])
        self.assertIn("population_in_zone", [c["name"] for c in r["tool_calls"]])


if __name__ == "__main__":
    unittest.main()
