#!/usr/bin/env python3
"""Frontend asset references stay resolvable after the folder split.

The browser app has no build step, so a renamed file is a 404 at runtime rather
than a compile error. These tests make the links between pages, stylesheets, and
the ``web/`` tree fail in CI instead.
"""

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = REPO_ROOT / "web"
ASSET_REFERENCE = re.compile(r'(?:src|href)="(/assets/[^"]+)"')
CSS_IMPORT = re.compile(r'@import url\("([^"]+)"\)')


class TestAssetReferences(unittest.TestCase):
    def test_every_asset_used_by_a_page_exists(self):
        for page in sorted((WEB_DIR / "pages").glob("*.html")):
            for reference in ASSET_REFERENCE.findall(page.read_text(encoding="utf-8")):
                with self.subTest(page=page.name, asset=reference):
                    target = WEB_DIR / reference.removeprefix("/assets/")
                    self.assertTrue(target.is_file(), f"{page.name} references missing {reference}")

    def test_legacy_css_manifests_import_real_files(self):
        for manifest in sorted((WEB_DIR / "css").glob("*.css")):
            for reference in CSS_IMPORT.findall(manifest.read_text(encoding="utf-8")):
                with self.subTest(manifest=manifest.name, asset=reference):
                    target = WEB_DIR / reference.removeprefix("/assets/")
                    self.assertTrue(target.is_file(), f"{manifest.name} imports missing {reference}")


if __name__ == "__main__":
    unittest.main()
