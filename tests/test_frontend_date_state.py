from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path


class FrontendDateStateTests(unittest.TestCase):
    def test_date_state_regressions(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not installed")
        repo_root = Path(__file__).resolve().parents[1]
        completed = subprocess.run(
            [node, str(repo_root / "tests" / "frontend_date_state_test.js")],
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)


if __name__ == "__main__":
    unittest.main()
