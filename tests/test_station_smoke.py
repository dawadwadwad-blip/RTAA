import json
from pathlib import Path
import sys
import tempfile
import unittest
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from station_smoke_contract import AXES, MESHES, REQUIRED_PROBES, json_bytes, read_bundle, sha, ue_position
from verify_station_smoke import check_report


class StationSmokeTest(unittest.TestCase):
    def test_meter_axes_match_the_pilot_contract(self):
        self.assertEqual(ue_position((100, 0, 0)), [10000, 0, 0])
        self.assertEqual(ue_position((0, 100, 0)), [0, -10000, 0])
        self.assertEqual(ue_position((0, 0, 1)), [0, 0, 100])

    def test_bundle_detects_a_changed_mesh_or_missing_probe(self):
        vertices = [[0, 0, 0], [100, 0, 0], [0, 100, 0]]
        geometry = json_bytes({"vertices": vertices, "triangles": [[0, 1, 2]]})
        metadata = {"sha256": sha(geometry), "triangles": 1, "bounds_cm": [[0, 0, 0], [100, 100, 0]]}
        manifest = {"version": 1, "axes": AXES, "meshes": dict.fromkeys(MESHES.values(), metadata),
                    "probes": [{"name": name, "mesh": "Terrain", "point_cm": [25, 25, 0]}
                               for name in sorted(REQUIRED_PROBES)]}
        with tempfile.TemporaryDirectory() as staging:
            path = Path(staging) / "station.zip"

            def write_package(terrain_geometry=geometry):
                with ZipFile(path, "w") as archive:
                    archive.writestr("manifest.json", json_bytes(manifest))
                    for asset in MESHES.values():
                        archive.writestr(asset + ".json", terrain_geometry if asset == "Terrain" else geometry)

            write_package()
            self.assertEqual(read_bundle(path)[0], manifest)
            write_package(geometry + b" ")
            with self.assertRaisesRegex(ValueError, "differs from its digest"):
                read_bundle(path)
            manifest["probes"].pop()
            write_package()
            with self.assertRaisesRegex(ValueError, "valid collision probes"):
                read_bundle(path)

    def test_report_must_match_manifest_map_and_package(self):
        target = "/Game/RVA/Tests/StationSmoke/Run_Test/StationSmoke"
        package = {"meshes": {"EastMain": {}}, "probes": [
            {"name": "station_crosswalk", "mesh": "EastMain", "point_cm": [200, 500, 600]}]}
        report = {"status": "PASS", "map": target, "mesh_count": 1, "package_sha256": "test-digest",
                  "probes": [{"name": "station_crosswalk", "mesh": "EastMain", "height_range_cm": [599, 601]}]}
        with tempfile.TemporaryDirectory() as staging:
            path = Path(staging) / "collision.json"
            path.write_text(json.dumps(report), encoding="utf-8")
            self.assertEqual(check_report(path, package, "test-digest", target), 1)
            with self.assertRaisesRegex(ValueError, "does not cover every asset and probe"):
                check_report(path, package, "different-digest", target)
            report["probes"] = []
            path.write_text(json.dumps(report), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "does not cover every asset and probe"):
                check_report(path, package, "test-digest", target)
