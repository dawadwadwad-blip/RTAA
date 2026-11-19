from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CivicCampaignRulesTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which("c++"), "A C++20 compiler is required")
    def test_compiled_campaign_math(self):
        include = ROOT / "Plugins/RVACivic/Source/RVACivic/Private"
        with tempfile.TemporaryDirectory() as directory:
            program = Path(directory) / "campaign_rules_test"
            subprocess.run(
                ["c++", "-std=c++20", "-Wall", "-Wextra", "-Werror", "-I", str(include),
                 str(ROOT / "tests/civic_campaign_rules_test.cpp"), "-o", str(program)],
                check=True, timeout=30)
            result = subprocess.run(
                [str(program)], check=True, capture_output=True, text=True, timeout=5)
            self.assertTrue(result.stdout.startswith("PASS:"))
