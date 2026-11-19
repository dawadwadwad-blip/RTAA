from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "Plugins/RVACivic/Source/RVACivic"


@unittest.skipUnless(shutil.which("c++"), "A C++20 compiler is required for the standalone gameplay tests.")
class CivicPolicyTest(unittest.TestCase):
    def compile_and_run(self, name, namespace):
        with tempfile.TemporaryDirectory() as directory:
            program = Path(directory) / name
            subprocess.run(
                ["c++", "-std=c++20", "-Wall", "-Wextra", "-Werror", "-I", str(SOURCE / namespace),
                 str(ROOT / "tests" / (name + ".cpp")), "-o", str(program)],
                check=True, timeout=30,
            )
            result = subprocess.run([str(program)], check=True, capture_output=True, text=True, timeout=5)
            self.assertTrue(result.stdout.startswith("PASS:"))

    def test_compiled_policy(self):
        self.compile_and_run("civic_policy_math_test", "Private")

    def test_standing_committee_progress(self):
        self.compile_and_run("standing_committee_progress_test", "Public")

    def test_night_shift_progress(self):
        self.compile_and_run("night_shift_progress_test", "Public")

    def test_church_hill_jobs(self):
        self.compile_and_run("church_hill_jobs_test", "Public")
