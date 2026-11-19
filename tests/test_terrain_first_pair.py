from importlib.util import find_spec
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import terrain_first_pair as terrain

HAS_GIS = all(find_spec(name) for name in ("laspy", "numpy", "rasterio", "pyproj"))


@unittest.skipUnless(HAS_GIS, "Install requirements-gis.txt to test terrain.")
class TerrainFirstPairTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.grid = terrain.load_json(ROOT / "pilot/grid.json")
        cls.manifest = terrain.load_json(ROOT / "pilot/tile_manifest.json")

    def test_bilinear_uses_pixel_centers_and_preserves_no_data(self):
        np = terrain.np
        native = np.array([[10, 12, 14], [20, 22, 24], [30, 32, np.nan]])
        transform = terrain.from_origin(100, 200, 1, 1)
        x, y = np.array([100.5, 101, 102, 90]), np.array([199.5, 199, 198, 199])
        result = terrain.bilinear(native, transform, x, y)
        self.assertEqual(list(result[:2]), [10, 16])
        self.assertTrue(np.isnan(result[2:]).all())

    def test_pack_rejects_missing_heights_and_overflow(self):
        np = terrain.np
        self.assertEqual(terrain.height_codes(np.array([-1, 0, 1]), self.grid).tolist(), [32640, 32768, 32896])
        for invalid in (np.nan, 256):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                terrain.height_codes(np.array([invalid]), self.grid)

    def test_output_r16_seam_order_and_geotiff_datum(self):
        np = terrain.np
        fixture_grid = dict(self.grid, tile_span_m=2)
        bounds = (100, 200, 104, 202)
        heights = np.arange(15).reshape(3, 5)
        codes = terrain.height_codes(heights, fixture_grid)
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            tiles = terrain.write_tiles(folder, heights, codes, fixture_grid, bounds)
            west, east = [np.fromfile(folder / t["heightmap"], dtype="<u2").reshape(3, 3) for t in tiles]
            np.testing.assert_array_equal(west[:, -1], east[:, 0])
            self.assertLess(west[0, 0], west[-1, 0])
            with terrain.rasterio.open(folder / tiles[1]["geotiff"]) as src:
                terrain.assert_compound_crs(terrain.pyproj.CRS.from_wkt(src.crs.to_wkt()),
                                            {"horizontal_epsg": 26918, "vertical_epsg": 5703}, src.name)
                self.assertEqual(src.xy(0, 0), (102, 202))
                np.testing.assert_array_equal(src.read(1), heights[:, 2:])

    def test_observed_crs_wins_over_catalog_assumption(self):
        reference = {"horizontal_epsg": 3748, "vertical_epsg": 5703}
        terrain.assert_compound_crs(terrain.pyproj.CRS("EPSG:3748+5703"), reference, "correct")
        with self.assertRaisesRegex(ValueError, "6347"):
            terrain.assert_compound_crs(terrain.pyproj.CRS("EPSG:6347+5703"), reference, "wrong horizontal CRS")

    def test_ground_candidates_keep_class_two_and_reject_withheld(self):
        np = terrain.np
        laspy = terrain.laspy
        hdr = laspy.LasHeader(point_format=6, version="1.4")
        hdr.add_crs(terrain.pyproj.CRS("EPSG:3748+5703"))
        cloud = laspy.LasData(hdr)
        cloud.x, cloud.y = np.array([25, 24, 75, 20]), np.array([25, 25, 75, 70])
        cloud.z = np.array([10, 20, 30, 5])
        cloud.classification = np.array([2, 2, 6, 9])
        cloud.withheld = np.array([0, 1, 0, 0])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fixture.las"
            cloud.write(path)
            ground, wet = terrain.read_ground_candidates(
                [path], {"horizontal_epsg": 3748, "vertical_epsg": 5703},
                terrain.pyproj.Transformer.from_pipeline("+proj=noop"), (0, 0, 100, 100),
            )
        np.testing.assert_array_equal(ground, np.array([[25, 25, 10]]))
        self.assertEqual(wet, {(2, 7)})

    def test_constant_vertical_bias_fails_registration(self):
        stats = terrain.residual_stats([-1.33] * 30)
        self.assertEqual(stats["median_signed_m"], -1.33)
        self.assertEqual(stats["outliers_over_one_m"], 30)
        self.assertFalse(stats["within_0_30_m_median_and_1_m_max"])
        self.assertTrue(terrain.residual_stats([0.05] * 30)["within_0_30_m_median_and_1_m_max"])

    def test_old_reference_keeps_two_sources_distinct(self):
        np = terrain.np
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "reference.tif"
            with terrain.rasterio.open(path, "w", driver="GTiff", height=20, width=20, count=1,
                                       dtype="float32", crs="EPSG:26918", nodata=-999999,
                                       transform=terrain.from_origin(0, 20, 1, 1)) as out:
                out.write(np.full((20, 20), 10, dtype="float32"), 1)
            record = {"asset": path.name, "sha256": terrain.digest(path), "bytes": path.stat().st_size,
                      "horizontal_epsg": 26918, "product_vertical_reference": "synthetic fixture"}
            points = [{"grid_en_m": [x, y], "dem_navd88_m": 10.07, "laz_navd88_m": 8.67}
                      for y in range(3, 8) for x in range(3, 8)]
            result = terrain.compare_reference(path, record, points)
            self.assertEqual(result["retained_samples"], 25)
            self.assertEqual(result["noaa_dem_minus_usgs_dem"]["median_absolute_m"], 0.07)
            self.assertEqual(result["noaa_laz_minus_usgs_dem"]["median_signed_m"], -1.33)

    def test_pair_extent(self):
        w, s, e, n = terrain.pair_extent(self.grid, self.manifest)
        self.assertAlmostEqual(e - w, 1008)
        self.assertAlmostEqual(n - s, 504)


if __name__ == "__main__":
    unittest.main()
