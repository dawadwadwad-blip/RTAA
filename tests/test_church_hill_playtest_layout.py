import math
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import build_church_hill_playtest as playtest


class ChurchHillPlaytestLayoutTest(unittest.TestCase):
    def test_ramp_top_surfaces_join_their_landings(self):
        for ramp in (playtest.GENTLE, playtest.DIRECT):
            with self.subTest(ramp=ramp.label):
                (x, y, z), (length, width, thickness), pitch = ramp.cube_transform()
                angle = math.radians(pitch)
                top_x = x - 50 * thickness * math.sin(angle)
                top_z = z + 50 * thickness * math.cos(angle)
                half_run = 50 * length * math.cos(angle)
                half_rise = 50 * length * math.sin(angle)
                self.assertAlmostEqual(top_x - half_run, ramp.x_start)
                self.assertAlmostEqual(top_z - half_rise, 0)
                self.assertAlmostEqual(top_x + half_run, playtest.LANDING_X)
                self.assertAlmostEqual(top_z + half_rise, playtest.LANDING_Z)
                self.assertEqual(y, ramp.y)
                self.assertEqual(width * 100, ramp.width)

    def test_route_gates_sit_on_distinct_drivable_grades(self):
        self.assertLess(playtest.GENTLE.grade, playtest.DIRECT.grade)
        self.assertLess(playtest.GENTLE.x_start, playtest.DIRECT.x_start)
        for anchor, ramp in (("GentleHill", playtest.GENTLE), ("DirectHill", playtest.DIRECT)):
            x, y, z = playtest.HILL_ANCHORS[anchor]
            self.assertLess(ramp.x_start, x)
            self.assertLess(x, playtest.LANDING_X)
            self.assertEqual(y, ramp.y)
            self.assertAlmostEqual(z, ramp.surface_z(x) + 70)
        for anchor in ("FinalGradeWarning", "StrapPullOff", "CorniceDelivery"):
            x, _, z = playtest.HILL_ANCHORS[anchor]
            self.assertGreater(x, playtest.LANDING_X)
            self.assertEqual(z, playtest.LANDING_Z + 70)

    def test_build_refuses_existing_and_invalid_maps_before_loading_any_classes(self):
        unreal = Mock()
        assets = unreal.get_editor_subsystem.return_value
        assets.does_asset_exist.return_value = True
        with self.assertRaisesRegex(RuntimeError, "already exists"):
            playtest.build(unreal, "VehicleMode", playtest.DEFAULT_MAP)
        with self.assertRaisesRegex(RuntimeError, "new Unreal package"):
            playtest.build(unreal, "VehicleMode", "/Engine/SomeMap")
        unreal.load_class.assert_not_called()
        assets.does_asset_exist.assert_called_once_with(playtest.DEFAULT_MAP)

    def test_missing_game_mode_never_creates_the_map(self):
        unreal = Mock()
        unreal.get_editor_subsystem.return_value.does_asset_exist.return_value = False
        unreal.load_class.return_value = None
        with self.assertRaisesRegex(RuntimeError, "GameMode class could not load"):
            playtest.build(unreal, "MissingMode", playtest.DEFAULT_MAP)
        unreal.get_editor_subsystem.assert_called_once_with(unreal.EditorAssetSubsystem)
