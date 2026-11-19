"""Validate the canonical v2 design data (not an Unreal gameplay test)."""
import json
from pathlib import Path
import unittest

CATALOG = Path(__file__).resolve().parents[1] / "design" / "v2_campaign.json"


class V2CampaignCatalogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(CATALOG.read_text(encoding="utf-8"))

    def test_acts_and_mission_sequence(self):
        self.assertEqual([(x["id"], x["mission_count"]) for x in self.data["acts"]],
                         [("I", 6), ("II", 8), ("III", 9), ("IV", 7)])
        missions = self.data["missions"]
        self.assertEqual(len(missions), 30)
        self.assertEqual([m["id"] for m in missions], list(range(1, 31)))
        self.assertEqual([m["act"] for m in missions],
                         ["I"] * 6 + ["II"] * 8 + ["III"] * 9 + ["IV"] * 7)
        self.assertEqual(len({m["title"] for m in missions}), 30)
        self.assertEqual(missions[0]["title"], "Night Shift")
        self.assertEqual(missions[-1]["title"], "Open House")

    def test_anchor_plot_beats(self):
        expected = {
            1: "forged_order_fire", 15: "ghost_project_reveal",
            16: "dell_betrayal", 21: "committee_parcel_plat",
            22: "cal_sells_share", 23: "house_fire_or_auction",
            25: "committee_freeze_procedure",
            29: "night_shift_log_podium_choice", 30: "porch_epilogue"
        }
        for mission_id, beat in expected.items():
            with self.subTest(mission=mission_id):
                self.assertEqual(self.data["missions"][mission_id - 1].get("beat"), beat)

    def test_groups_wings_and_geography(self):
        groups = self.data["groups"]
        self.assertEqual(len(groups), 5)
        codes = {g["code"] for g in groups}
        self.assertEqual(codes, {"albanico", "pod", "transit", "asphalt", "independents"})
        for group in groups:
            self.assertTrue(group["believer"])
            self.assertTrue(group["means"])
            self.assertTrue(group["secondary"])
        self.assertIn("Church Hill", next(g for g in groups if g["code"] == "albanico")["hq"])
        self.assertIn("Scott's Addition", next(g for g in groups if g["code"] == "pod")["hq"])
        for mission in self.data["missions"]:
            self.assertTrue(set(mission.get("factions", [])) <= codes)

    def test_mechanics_and_endings(self):
        mechanics = self.data["gameplay"]
        self.assertEqual(mechanics["work_order_verbs"],
                         ["stripe", "patch", "tow", "deliver", "swap", "block", "tail"])
        self.assertEqual(mechanics["method_dial"], ["Kind", "Pointed", "Hard"])
        self.assertEqual(mechanics["road_segment_states"],
                         ["normal", "bike_lane", "closed", "reversed"])
        self.assertEqual(mechanics["net_good_fields"],
                         ["helped_households", "harmed_households"])
        self.assertEqual((mechanics["strain_min"], mechanics["strain_max"]), (0, 3))
        self.assertEqual(mechanics["endings"],
                         ["Built", "Frozen", "Third Alignment", "The Fixer"])

    def test_no_phantom_implementation_claim(self):
        self.assertEqual(self.data["status"], "design_data_not_playable_content")


if __name__ == "__main__":
    unittest.main()
