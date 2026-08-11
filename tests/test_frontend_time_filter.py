import shutil
import subprocess
import unittest
from pathlib import Path


class FrontendTimeFilterTests(unittest.TestCase):
    def test_time_filter_regressions(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js is unavailable")

        repo_root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [node, str(repo_root / "tests" / "frontend_time_filter_test.js")],
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
