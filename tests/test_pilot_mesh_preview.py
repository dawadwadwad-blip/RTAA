from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import build_pilot_mesh_preview as preview


@unittest.skipIf(preview.shapely is None, "Install requirements-gis.txt to test the preview.")
class PilotMeshPreviewTest(unittest.TestCase):
    def test_grade_drape_uses_the_same_triangles_as_the_mesh(self):
        heights = preview.np.array([[0, 1], [2, 11]], dtype=float)
        surface = preview.Surface(heights, (0, 0, 1, 1), 1)
        self.assertAlmostEqual(surface.height(0.25, 0.25), 3.75)
        self.assertAlmostEqual(surface.height(0.75, 0.75), 3.25)
        self.assertAlmostEqual(surface.height(1, 0), 11)

    def test_flagged_spans_stay_out_of_ground_drape(self):
        obj = preview.Obj()
        surface = preview.Surface(preview.np.zeros((3, 3)), (0, 0, 2, 2), 1)
        street = {"a": 1, "b": 2, "highway": "residential", "bridge": False,
                  "tunnel": False, "layer": 0, "forward": ["car"], "backward": ["car"]}
        graph = {"nodes": [{"id": 1, "local_en_m": [0, 1]}, {"id": 2, "local_en_m": [2, 1]}],
                 "edges": [street, {**street, "bridge": True}, {**street, "layer": -1}]}
        counts = preview.transport(obj, surface, graph)
        self.assertEqual(counts["ordinary_road_edges"], 1)
        self.assertEqual(counts["grade_separated_edges_omitted"], 2)
        self.assertEqual(obj.faces, 2)

    def test_approach_overlay_follows_nonplanar_terrain_and_preserves_openings(self):
        from station_approach import Drape

        surface = preview.Surface(preview.np.array([[3, 6, 2], [2, 11, 1], [0, 3, 9]], dtype=float),
                                  (0, 0, 2, 2), 1)
        obj = preview.Obj()
        drape = Drape(obj, surface)
        opening = preview.box(0.67, 0.59, 1.37, 1.32)
        polygon = preview.box(0.14, 0.24, 1.81, 1.93).difference(opening)
        drape.add(polygon, "test", lambda _x, _y: 0.065)
        vertices = [tuple(map(float, line.split()[1:])) for line in obj.lines if line.startswith("v ")]
        area = 0.0
        for line in obj.lines:
            if line.startswith("f "):
                points = [vertices[int(index) - 1] for index in line.split()[1:]]
                triangle = preview.Polygon([point[:2] for point in points])
                self.assertLess(triangle.intersection(opening).area, 1e-8)
                self.assertAlmostEqual(sum(z for _, _, z in points) / 3,
                                       surface.height(triangle.centroid.x, triangle.centroid.y) + 0.065, places=4)
                area += triangle.area
        self.assertAlmostEqual(area, polygon.area, places=6)

    def test_replaced_ground_ribbon_keeps_ends_and_excludes_decks(self):
        class ApproachMask:
            def legacy_mask(self, _way):
                return preview.box(4, 0, 6, 10)

        obj = preview.Obj()
        surface = preview.Surface(preview.np.zeros((6, 6)), (0, 0, 10, 10), 2)
        street = {"a": 1, "b": 2, "highway": "residential", "bridge": False,
                  "tunnel": False, "layer": 0, "forward": ["car"], "backward": ["car"]}
        graph = {"nodes": [{"id": 1, "local_en_m": [0, 5]}, {"id": 2, "local_en_m": [10, 5]}],
                 "edges": [street, {**street, "bridge": True}]}
        counts = preview.transport(obj, surface, graph, ApproachMask())
        xs = [float(line.split()[1]) for line in obj.lines if line.startswith("v ")]
        self.assertEqual((min(xs), max(xs)), (0, 10))
        self.assertTrue(all(x <= 4 or x >= 6 for x in xs))
        self.assertEqual(counts["partially_or_fully_replaced_ground_edges"], 1)
        self.assertEqual(counts["grade_separated_edges_omitted"], 1)
