"""Guard the distinction between observed road tops and an occluded rail span."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import station_deck_profile as decks


@unittest.skipIf(decks.laspy is None, "Install the project GIS dependencies for deck profile tests.")
class StationDeckProfileTests(unittest.TestCase):
    def test_rail_interpolates_only_between_observed_anchors(self):
        np = decks.np
        rail = decks.CORRIDORS[-1]
        distance = np.arange(0, 105, 5, dtype=float)
        samples = 12.0 + 0.008 * distance
        samples[4:17] = np.nan
        out, gaps, grade = decks.interpolate_profile(distance, samples, rail)
        self.assertEqual(gaps, [(3, 17, 70.0)])
        self.assertAlmostEqual(out[10], 12.4)
        self.assertAlmostEqual(grade, 0.008)
        samples[0] = np.nan
        with self.assertRaisesRegex(ValueError, "extrapolation"):
            decks.interpolate_profile(distance, samples, rail)

    def test_road_profile_refuses_a_long_gap_or_sudden_other_layer(self):
        np = decks.np
        road = decks.CORRIDORS[0]
        distance = np.arange(0, 60, 5, dtype=float)
        samples = np.full(distance.shape, 25.0)
        samples[3:7] = np.nan
        with self.assertRaisesRegex(ValueError, "gap"):
            decks.interpolate_profile(distance, samples, road)
        samples[3:7] = 25.0
        samples[5] = 28.0
        with self.assertRaisesRegex(ValueError, "grade"):
            decks.interpolate_profile(distance, samples, road)

    def test_rail_band_rejects_freeway_points_in_same_xy_neighborhood(self):
        np = decks.np
        line = decks.LineString([(0, 0), (30, 0)])
        lower = [(x, y, 13.2) for x in range(0, 12) for y in np.linspace(-1.0, 1.0, 12)]
        upper = [(x, y, 26.2) for x in range(0, 31) for y in np.linspace(-1.0, 1.0, 12)]
        points = np.array(lower + upper)
        _, _, observed, _, _ = decks.match_returns(line, decks.CORRIDORS[-1], points, decks.cKDTree(points[:, :2]))
        self.assertAlmostEqual(observed[0], 13.2)
        self.assertTrue(np.isnan(observed[-1]))

    def test_local_alignment_requires_holdout_agreement(self):
        class Flat:
            def height(self, x, y):
                return 7.0

        np = decks.np
        w, s, e, n = decks.FIT_EXTENT
        origin = [(x, y) for x in range(w, e, 8) for y in range(s, n, 8)]
        stable = np.array([(x, y, 5.65) for x, y in origin])
        correction, stats = decks.fit_local_alignment(stable, Flat())
        self.assertAlmostEqual(correction, 1.35)
        self.assertEqual(stats["holdout_p95_abs_m"], 0.0)
        biased = np.array([(x, y, 5.65 if ((x - w) // 8 + (y - s) // 8) % 2 == 0 else 6.0)
                           for x, y in origin])
        with self.assertRaisesRegex(ValueError, "withheld"):
            decks.fit_local_alignment(biased, Flat())


if __name__ == "__main__":
    unittest.main()
