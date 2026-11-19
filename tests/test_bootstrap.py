import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from zipfile import ZipFile


TOOLS = Path(__file__).resolve().parents[1] / "tools"


class BootstrapTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.bundle = self.root / "baseline.zip"

    def write_bundle(self, *, match_count=1):
        with ZipFile(self.bundle, "w") as archive:
            archive.writestr("kit/Richmond_OpenStreetMap_ODbL.json", '{"buildings":[[],[]]}')
            archive.writestr("kit/Richmond_2025_Roof_Heights.json",
                             json.dumps({"heights": [[21, 20, 10], None], "matchCount": match_count}))
            archive.writestr("kit/Site_Reference.json", '{"routeLengthMetres":20.1234}')
            archive.writestr("kit/Route_Centerline.csv", "chainage_m,east_m\n0,0\n20.123,18\n")
            archive.writestr("kit/Mesh.fbx", b"test")
            archive.writestr("kit/Brick.png", b"test")
            archive.writestr("kit/Import_Richmond.py", "raise RuntimeError('archive was executed')")

    def run_command(self, *args):
        return subprocess.run(
            [sys.executable, str(TOOLS / "run_task.py"), "S0-01", "--", *args],
            cwd=self.root, capture_output=True, text=True, timeout=15,
        )

    def run_inventory(self, *args):
        return self.run_command("python", str(TOOLS / "baseline_inventory.py"),
                                "--bundle", self.bundle.name, *args)

    def runs(self):
        return [json.loads(path.read_text()) for path in sorted(self.root.glob("reports/runs/*.json"))]

    def test_retry_report_is_stable_and_preserves_input_and_notes(self):
        self.write_bundle()
        source = self.bundle.read_bytes()
        ledger = self.root / "DEV_STATE.md"
        ledger.write_text("# Development notes\n\nKeep this note.\n")
        html = self.root / "browser.html"
        html.write_text("fixture")
        report_path = self.root / "reports/baseline.json"
        self.assertEqual(self.run_inventory("--html", html.name).returncode, 0)
        baseline = report_path.read_bytes()
        ledger.write_text(ledger.read_text() + "\nKeep this later note too.\n")
        self.assertEqual(self.run_inventory("--html", html.name).returncode, 0)
        self.assertEqual(baseline, report_path.read_bytes())
        self.assertEqual(self.bundle.read_bytes(), source)
        self.assertEqual([run["status"] for run in self.runs()], ["PASS", "PASS"])
        self.assertEqual(len({run["run_id"] for run in self.runs()}), 2)
        self.assertIn("Keep this note.", ledger.read_text())
        self.assertIn("Keep this later note too.", ledger.read_text())
        self.assertEqual(json.loads(baseline)["counts"]["lidar_matches"], 1)

    def test_missing_required_input_is_blocked(self):
        self.assertEqual(self.run_inventory().returncode, 3)
        self.assertEqual(self.runs()[0]["status"], "BLOCKED")
        self.assertIn("Missing baseline ZIP", self.runs()[0]["blocker"])
        self.assertIn("BLOCKED", (self.root / "DEV_STATE.md").read_text())

    def test_corrupt_zip_preserves_last_good_inventory(self):
        self.write_bundle()
        self.assertEqual(self.run_inventory().returncode, 0)
        report = self.root / "reports/baseline.json"
        before = report.read_bytes()
        self.bundle.write_bytes(b"not a ZIP")
        self.assertEqual(self.run_inventory().returncode, 1)
        self.assertEqual(self.runs()[-1]["status"], "FAILED")
        self.assertEqual(report.read_bytes(), before)

    def test_metadata_mismatch_is_reported(self):
        self.write_bundle(match_count=2)
        result = self.run_inventory()
        self.assertEqual(result.returncode, 1)
        self.assertIn("FAIL: count matches reported LiDAR total", result.stdout)

    def test_interrupted_run_is_reconciled_once(self):
        self.write_bundle()
        self.assertEqual(self.run_inventory().returncode, 0)
        run = self.runs()[0]
        run.update(status="RUNNING", finished_at=None, exit_code=None)
        stale = self.root / "reports/runs" / (run["run_id"] + ".json")
        stale.write_text(json.dumps(run))
        self.assertEqual(self.run_inventory().returncode, 0)
        prior = stale.read_bytes()
        self.assertEqual(self.run_inventory().returncode, 0)
        self.assertEqual(stale.read_bytes(), prior)
        self.assertEqual(self.runs()[0]["status"], "INTERRUPTED")
        self.assertIsNone(self.runs()[0]["exit_code"])
        self.assertEqual((self.root / "DEV_STATE.md").read_text().count("**INTERRUPTED**"), 1)

    def test_child_launch_failure_still_writes_evidence(self):
        result = self.run_command(str(self.root / "no-such-program"))
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.runs()[0]["status"], "FAILED")
        self.assertTrue((self.root / self.runs()[0]["log"]).exists())


if __name__ == "__main__":
    unittest.main()
