"""Core tests (run: cd backend && python -m pytest -q). Plain asserts; also runnable with unittest."""
import math
import unittest

import numpy as np

from app.alerts.composer import _fmt_int, _numbers_ok, facts_for
from app.data.population import get_population
from app.data.synthetic import EventSpec, Grid, climatology, demo_scenario, generate_forecast
from app.geo import ellipse_polygon, haversine_km, points_in_polygon, polygon_area_km2
from app.pipeline import impact as imp
from app.pipeline.detection import detect
from app.pipeline.preprocess import standardise
from app.pipeline.tracking import associate, motion


class GeoTests(unittest.TestCase):
    def test_haversine_known_distance(self):
        # Bengaluru - Chennai ~ 290 km great-circle
        d = float(haversine_km(12.9716, 77.5946, 13.0827, 80.2707))
        self.assertAlmostEqual(d, 290, delta=6)

    def test_circle_area_and_containment(self):
        ring = ellipse_polygon(12.97, 77.59, 5, 5, n=96)
        self.assertAlmostEqual(polygon_area_km2(ring), math.pi * 25, delta=1.0)
        inside = points_in_polygon(np.array([77.59, 77.80]), np.array([12.97, 12.97]), ring)
        self.assertEqual(list(inside), [True, False])


class PopulationTests(unittest.TestCase):
    def test_official_data_loaded(self):
        pop = get_population()
        self.assertEqual(len(pop.wards), 198)
        self.assertGreater(len(pop.districts), 500)

    def test_zone_population_reasonable(self):
        pop = get_population()
        z = pop.in_polygon(ellipse_polygon(12.9716, 77.5946, 3, 3))   # central Bengaluru
        self.assertIn("Census 2011 · BBMP ward", z["sources"])
        self.assertTrue(100_000 < z["total"] < 1_500_000)
        sea = pop.in_polygon(ellipse_polygon(15.0, 88.0, 5, 5))       # Bay of Bengal
        self.assertEqual(sea["total"], 0)


class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.grid = Grid()
        # single, strong, well-separated event for a deterministic check
        cls.ev = EventSpec("T1", "heavy_rainfall", 16.0, 79.0, 15, 270, 24, 96, 8.0, 60)
        cls.bundle = generate_forecast(cls.grid, 9, [cls.ev], members=4, seed=3)
        cls.pre = standardise(cls.bundle, climatology(cls.grid, 9))
        cls.objs = detect(cls.bundle, cls.pre)

    def test_preprocess_fills_missing(self):
        for v, a in self.pre.z.items():
            self.assertFalse(np.isnan(a).any(), v)

    def test_event_is_detected_near_truth(self):
        peak_h = self.ev.start_h + self.ev.duration_h / 2
        lat, lon = self.ev.position(peak_h)
        near = [o for o in self.objs if o.lead_h == int(peak_h) and haversine_km(o.lat, o.lon, lat, lon) < 80]
        self.assertTrue(near, "event not detected within 80 km of its true position")

    def test_tracking_recovers_motion(self):
        for o in self.objs:   # rule-based typing is enough for the tracker
            o.type = "heavy_rainfall"
        tracks = associate(self.objs, 6)
        longest = max(tracks, key=lambda t: len(t.points))
        self.assertGreaterEqual(len(longest.points), 6)
        speed, heading, _, _ = motion(longest.points, n=6)
        self.assertAlmostEqual(speed, 15, delta=7)
        self.assertLess(abs((heading - 270 + 180) % 360 - 180), 30)


class ImpactTests(unittest.TestCase):
    def test_rings_nested_and_adaptive(self):
        z = imp.zone_geometry(12.97, 77.59, 6.0, 20, 90, 30)
        a = [polygon_area_km2(z["rings"][r]) for r in ("high", "moderate", "low")]
        self.assertTrue(a[0] < a[1] < a[2])
        z_weak = imp.zone_geometry(12.97, 77.59, 3.0, 0, 0, 0)
        self.assertGreater(z["radii_km"]["low"], z_weak["radii_km"]["low"])

    def test_vehicle_heading_into_zone_is_flagged(self):
        z = imp.zone_geometry(12.97, 77.59, 5.0, 0, 0, 10)
        from app.geo import destination
        la, lo = destination(12.97, 77.59, 90, 20)        # 20 km east of the zone
        toward = {"id": "V1", "lat": la, "lon": lo, "heading_deg": 270, "speed_kmh": 40}
        away = {"id": "V2", "lat": la, "lon": lo, "heading_deg": 90, "speed_kmh": 40}
        res = imp.vehicles_toward(z, [toward, away])
        self.assertEqual([v["id"] for v in res], ["V1"])
        self.assertTrue(10 <= res[0]["eta_min"] <= 25)


class AlertTests(unittest.TestCase):
    def test_indian_number_format(self):
        self.assertEqual(_fmt_int(883933), "8,83,933")
        self.assertEqual(_fmt_int(12345678), "1,23,45,678")

    def test_invented_numbers_rejected(self):
        f = {"people_total": 883933, "people_high": 33456, "speed_kmh": 11, "probability_pct": 83}
        self.assertTrue(_numbers_ok("About 8,83,933 people; 83% agree; 11 km/h.", f))
        self.assertFalse(_numbers_ok("About 9,50,000 people are at risk.", f))


if __name__ == "__main__":
    unittest.main()


class AccountTests(unittest.TestCase):
    def test_password_hash_and_determinism(self):
        from app.accounts import check_password, demo_password, hash_password
        self.assertEqual(demo_password("X"), demo_password("X"))
        self.assertNotEqual(demo_password("X"), demo_password("Y"))
        h = hash_password("Monsoon@1234")
        self.assertTrue(check_password("Monsoon@1234", h))
        self.assertFalse(check_password("monsoon@1234", h))

    def test_institution_names_unique(self):
        from app.data.synthetic import generate_assets
        names = [a["name"].lower() for a in generate_assets()]
        self.assertEqual(len(names), len(set(names)))
