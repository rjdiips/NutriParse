#!/usr/bin/env python3
"""The browser config loader's fallback rules, exercised with Node.

The app has no JavaScript test runner of its own yet, so the fallback behaviour
is pinned by Node's built-in test runner and this Python test keeps it in the
normal suite.
"""

import shutil
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
NODE = shutil.which("node")
TEST_SCRIPT = REPO_ROOT / "tests" / "config_client.test.cjs"


@unittest.skipUnless(NODE, "Node.js is not installed")
class TestConfigClient(unittest.TestCase):
    def test_waits_and_fallback_behaviour(self):
        result = subprocess.run(
            [NODE, "--test", str(TEST_SCRIPT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, f"{result.stdout}\n{result.stderr}")


if __name__ == "__main__":
    unittest.main()
