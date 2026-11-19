from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CivicPolicyTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which("c++"), "A C++20 compiler is required for the standalone policy test.")
    def test_compiled_policy(self):
        include = ROOT / "Plugins/RVACivic/Source/RVACivic/Private"
        with tempfile.TemporaryDirectory() as directory:
            program = Path(directory) / "civic_policy_math_test"
            subprocess.run(
                ["c++", "-std=c++20", "-Wall", "-Wextra", "-Werror", "-I", str(include),
                 str(ROOT / "tests/civic_policy_math_test.cpp"), "-o", str(program)],
                check=True, timeout=30,
            )
            result = subprocess.run([str(program)], check=True, capture_output=True, text=True, timeout=5)
            self.assertTrue(result.stdout.startswith("PASS:"))
