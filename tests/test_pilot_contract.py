import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import pilot_contract as pilot


@unittest.skipUnless(importlib.util.find_spec("pyproj"), "Install requirements-gis.txt to test the pilot grid.")
class PilotContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.grid = pilot.load_json(ROOT / "pilot/grid.json")
        cls.controls = pilot.load_json(ROOT / "pilot/controls.json")
        cls.catalog = pilot.load_json(ROOT / "data/catalog.json")
        cls.manifest, cls.coverage, cls.checks = pilot.make_contract(cls.grid, cls.controls, cls.catalog)

    def test_origin_and_axes(self):
        easting, northing = self.manifest["origin_grid_m_en"]
        self.assertAlmostEqual(easting, 286036.805939, places=3)
        self.assertAlmostEqual(northing, 4156591.390745, places=3)
        self.assertEqual(pilot.unreal_position(self.grid, 100, 0, 0), (10000, 0, 0))
        self.assertEqual(pilot.unreal_position(self.grid, 0, 100, 0), (0, -10000, 0))
        self.assertEqual(pilot.unreal_position(self.grid, 0, 0, 1), (0, 0, 100))

    def test_terrain_bounds_tile_seam_and_halo(self):
        self.assertEqual(len(self.manifest["tiles"]), 12)
        self.assertEqual(self.manifest["vertices_per_axis"], 505)
        self.assertEqual(self.manifest["acquisition_local_bounds_m"], [-1108, -1108, 604, 1108])
        a, b = self.manifest["first_adjacent_tiles_en"]
        w1, s1, e1, n1 = pilot.tile_bounds(*a, 504)
        w2, s2, _, n2 = pilot.tile_bounds(*b, 504)
        self.assertEqual((e1, s1, n1), (w2, s2, n2))
        self.assertEqual([w1 + i for i in range(505)][-1], w2)
        self.assertEqual(pilot.cover_tiles([-504, 0, 504, 504], 504), [(-1, 0), (0, 0)])

    def test_landscape_height_quantization(self):
        self.assertEqual(pilot.height_code(self.grid, -256), 0)
        self.assertEqual(pilot.height_code(self.grid, 1), 32896)
        self.assertEqual(pilot.height_code(self.grid, 255.9921875), 65535)
        with self.assertRaises(ValueError):
            pilot.height_code(self.grid, 256)

    def test_versioned_controls_and_expected_offsets(self):
        expected_cm = [(-77544.6, -35846.3), (23921.6, -992.0), (40031.3, 42994.3)]
        for point, expected in zip(self.manifest["controls"], expected_cm, strict=True):
            for observed, target in zip(point["unreal_centimeters_xy_only"], expected, strict=True):
                self.assertAlmostEqual(observed, target, delta=0.2)
        self.assertTrue(all(self.checks.values()))
        self.assertGreater(self.manifest["plan_view_control_triangle_area_m2"], 100000)

    def test_exports_match_inputs(self):
        self.assertEqual(self.manifest, pilot.load_json(ROOT / "pilot/tile_manifest.json"))
        self.assertEqual(self.coverage, pilot.load_json(ROOT / "pilot/coverage.geojson"))

    def test_mismatching_raw_capture_is_rejected(self):
        with tempfile.TemporaryDirectory() as files:
            capture = Path(files) / "changed.osm"
            capture.write_text("<osm />")
            with self.assertRaisesRegex(ValueError, "differ from the locked response"):
                pilot.audit_osm_capture(capture, self.controls)


if __name__ == "__main__":
    unittest.main()
