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
