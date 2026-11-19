from pathlib import Path
import sys
import unittest
from xml.etree import ElementTree

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import pilot_street_graph as graph


class PilotStreetGraphTest(unittest.TestCase):
    def test_mode_specific_access_and_one_way(self):
        self.assertEqual(graph.permitted_directions(
            {"highway": "residential", "oneway": "-1"}), [["foot"], ["car", "foot"]])
        self.assertEqual(graph.permitted_directions(
            {"highway": "primary", "junction": "roundabout", "oneway": "no"}),
            [["car", "foot"], ["car", "foot"]])
        self.assertEqual(graph.permitted_directions(
            {"highway": "service", "access": "private", "foot": "yes"}), [["foot"], ["foot"]])
        self.assertEqual(graph.permitted_directions(
            {"highway": "footway", "bridge": "yes", "oneway:foot": "yes"}), [["foot"], []])
        self.assertEqual(graph.permitted_directions(
            {"highway": "primary", "oneway": "reversible"}), [["foot"], ["foot"]])

    def test_grade_separation_uses_osm_node_identity(self):
        raw = ElementTree.fromstring("""
        <osm>
          <way id="10" version="1"><nd ref="1"/><nd ref="2"/>
            <tag k="highway" v="primary"/><tag k="bridge" v="yes"/></way>
          <way id="20" version="1"><nd ref="3"/><nd ref="4"/>
            <tag k="highway" v="residential"/></way>
          <way id="30" version="1"><nd ref="2"/><nd ref="5"/>
            <tag k="highway" v="residential"/></way>
        </osm>""")
        positions = {1: [-2, 0], 2: [2, 0], 3: [0, -2], 4: [0, 2], 5: [3, 0]}
        nodes = {key: {"local_en_m": xy} for key, xy in positions.items()}
        edges = graph.street_edges(raw, nodes, [-1, -1, 3, 1])
        self.assertEqual([edge["way"] for edge in edges], [10, 20, 30])
        self.assertTrue(graph.cross_interior(*(positions[i] for i in (1, 2, 3, 4))))
        _, car = graph.arc_index(edges, "car")
        self.assertEqual({arc["way"] for arc in car[2]}, {10, 30})
        self.assertEqual({arc["way"] for arc in car[3]}, {20})

    def test_turn_restrictions_keep_same_way_through_travel(self):
        raw = ElementTree.fromstring("""
        <osm>
          <relation id="101" version="1">
            <member type="way" ref="10" role="from"/><member type="node" ref="2" role="via"/>
            <member type="way" ref="10" role="to"/>
            <tag k="type" v="restriction"/><tag k="restriction" v="no_u_turn"/>
          </relation>
          <relation id="102" version="1">
            <member type="way" ref="20" role="from"/><member type="node" ref="2" role="via"/>
            <member type="way" ref="10" role="to"/>
            <tag k="type" v="restriction"/><tag k="restriction" v="only_right_turn"/>
          </relation>
          <relation id="103" version="1">
            <member type="way" ref="10" role="from"/><member type="way" ref="20" role="via"/>
            <member type="way" ref="30" role="to"/>
            <tag k="type" v="restriction"/><tag k="restriction" v="no_u_turn"/>
          </relation>
        </osm>""")
        edges = [{"id": letter, "way": way, "a": a, "b": b, "forward": ["car"], "backward": ["car"]}
                 for letter, way, a, b in (("a", 10, 1, 2), ("b", 10, 2, 3), ("c", 20, 4, 2))]
        blocked, unresolved = graph.turn_restrictions(raw, *graph.arc_index(edges, "car"))
        self.assertEqual([(r["incoming_edge"], r["outgoing_edge"]) for r in blocked],
                         [("a", "a"), ("b", "b"), ("c", "c")])
        self.assertEqual([(r["relation"], r["reason"]) for r in unresolved],
                         [(103, "unsupported_member_configuration")])
