import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import verify_church_hill as runner


class ChurchHillEngineRunnerTest(unittest.TestCase):
    def read_report(self, entries):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "index.json"
            report.write_text(json.dumps({"tests": entries}), encoding="utf-8-sig")
            return runner.check_report(report)

    def test_report_covers_each_expected_native_scenario(self):
        entries = [{"fullTestPath": name, "state": "Success", "errors": 0} for name in runner.TESTS]
        self.assertEqual(self.read_report(entries), list(runner.TESTS))
        with self.assertRaisesRegex(ValueError, "found 0"):
            self.read_report(entries[:1])
        with self.assertRaisesRegex(ValueError, "found 2"):
            self.read_report(entries + entries[:1])

    def test_failed_skipped_or_incomplete_test_does_not_pass(self):
        first = {"fullTestPath": runner.TESTS[0], "state": "Success", "errors": 0}
        for status, errors in (("Fail", 1), ("Skipped", 0), ("InProcess", 0), ("Success", 1)):
            with self.subTest(status=status, errors=errors):
                second = {"fullTestPath": runner.TESTS[1], "state": status, "errors": errors}
                with self.assertRaisesRegex(ValueError, runner.TESTS[1]):
                    self.read_report([first, second])
