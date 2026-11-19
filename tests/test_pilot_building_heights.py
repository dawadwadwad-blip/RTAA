from pathlib import Path
import sys
import unittest
from xml.etree import ElementTree

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import pilot_building_heights as heights


@unittest.skipIf(heights.laspy is None, "Install requirements-gis.txt for the building height checks.")
class PilotBuildingHeightTest(unittest.TestCase):
    def test_forecourt_multipolygon_keeps_the_inner_ring(self):
        source = ElementTree.fromstring("""
        <osm>
          <way id="1" version="1"><nd ref="1"/><nd ref="2"/><nd ref="3"/>
            <tag k="building" v="yes"/></way>
          <way id="2" version="1"><nd ref="1"/><nd ref="4"/><nd ref="3"/></way>
          <way id="3" version="1"><nd ref="5"/><nd ref="6"/><nd ref="7"/><nd ref="8"/><nd ref="5"/></way>
          <relation id="44" version="3">
            <member type="way" ref="1" role="outer"/><member type="way" ref="2" role="outer"/>
            <member type="way" ref="3" role="inner"/>
            <tag k="type" v="multipolygon"/><tag k="building" v="church"/>
          </relation>
        </osm>""")
        coordinates = [(0, 0), (8, 0), (8, 8), (0, 8), (2, 2), (4, 2), (4, 4), (2, 4)]
        nodes = {i: {"local_en_m": xy} for i, xy in enumerate(coordinates, 1)}
        footprints, context, invalid = heights.extract_footprints(source, nodes, heights.box(-1, -1, 9, 9))
        self.assertEqual((len(context), invalid), (1, []))
        self.assertEqual(footprints[0][:2], ("osm/relation/44", 3))
        self.assertAlmostEqual(footprints[0][3].area, 60)
        self.assertFalse(heights.shapely.contains_xy(footprints[0][3], 3, 3))

    def test_relative_height_ignores_a_shared_vertical_offset(self):
        roof = heights.np.array([(x + 0.1, y + 0.1, 17.0) for x in range(5) for y in range(5)])
        ground = heights.np.array([(x + 0.1, -1.0, 5.0) for x in range(25)])
        footprint = heights.box(0, 0, 5, 5)
        first = heights.measure(footprint, roof, ground)
        offset = heights.np.array([0.0, 0.0, 1.33])
        self.assertEqual(first, heights.measure(footprint, roof + offset, ground + offset))
        self.assertEqual(first["relative_lidar_candidate_m"], 12.0)
        self.assertEqual(first["quality_flags"], [])

    def test_sparse_or_uneven_measurements_are_flagged(self):
        roof = heights.np.array([[1.0, 1.0, 10.0]])
        ground = heights.np.array([[0.0, 0.0, x] for x in range(30)])
        data = heights.measure(heights.box(0, 0, 6, 6), roof, ground)
        self.assertIn("sparse_class_6", data["quality_flags"])
        self.assertIn("varied_nearby_ground", data["quality_flags"])
        self.assertIn("implausible_height", data["quality_flags"])
        self.assertEqual(heights.tag_height({"height": "20 ft"}), (6.096, "osm_height"))
        self.assertEqual(heights.tag_height({"building:levels": "3"}), (9.8, "osm_levels_estimate"))
        self.assertEqual(heights.tag_height({"height": "unmeasured"}), (None, "unresolved"))
