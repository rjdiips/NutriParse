#!/usr/bin/env python3
"""The browser JavaScript type-check stays green.

The frontend is plain classic JavaScript, so a misspelled shared global fails at
runtime rather than at build time. This test runs ``npm run check:js`` and skips
when the dev-only Node tooling has not been installed.
"""

import os
import shutil
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
NPM = shutil.which("npm")
TYPESCRIPT = REPO_ROOT / "node_modules" / "typescript"


@unittest.skipUnless(NPM and TYPESCRIPT.is_dir(), "npm install has not been run")
class TestJavaScriptTypeCheck(unittest.TestCase):
    def test_check_js_passes(self):
        result = subprocess.run(
            [NPM, "run", "check:js"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=180,
            shell=os.name == "nt",
        )
        self.assertEqual(result.returncode, 0, f"{result.stdout}\n{result.stderr}")


if __name__ == "__main__":
    unittest.main()
