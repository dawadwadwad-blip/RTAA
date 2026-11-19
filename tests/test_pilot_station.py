import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import plan_pilot_station as station


class PilotStationTest(unittest.TestCase):
    def test_affine_moves_the_spawn_relative_axis_once(self):
        spawn = (-359.0, 472.0, 11.0)

        def projection(x, y):
            return x + 0.025 * y + 16.0, y - 0.026 * x + 4.0

        matrix, legacy_clock, projected_clock = station.affine_around(projection, spawn, (-704.0, 309.0))
        self.assertEqual(legacy_clock, (-345.0, -163.0))
        for legacy in (legacy_clock, (-248.0, -22.0), (-333.5, -80.25)):
            result = tuple(a * legacy[0] + b * legacy[1] + t for a, b, t in matrix)
            expected = projection(legacy[0] + spawn[0], legacy[1] + spawn[1])
            self.assertLess(math.dist(result, expected), 1e-8)
        self.assertEqual(projected_clock, projection(-704.0, 309.0))
