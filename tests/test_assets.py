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
SCRIPT_TAG = re.compile(r"<script\b([^>]*)>", re.IGNORECASE)
MODULE_SPECIFIER = re.compile(r'(?:\bfrom|\bimport)\s+[\'"]((?:\.{1,2}/|/)[^\'"]+)[\'"]')


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

    def test_every_module_import_resolves_to_a_file(self):
        for script in sorted((WEB_DIR / "js").rglob("*.js")):
            source = script.read_text(encoding="utf-8")
            for specifier in MODULE_SPECIFIER.findall(source):
                with self.subTest(script=script.name, specifier=specifier):
                    if specifier.startswith("/assets/"):
                        target = WEB_DIR / specifier.removeprefix("/assets/")
                    else:
                        target = (script.parent / specifier).resolve()
                    self.assertTrue(target.is_file(), f"{script.name} imports missing {specifier}")


class TestComposeModuleGraph(unittest.TestCase):
    def test_compose_page_loads_one_module_entry(self):
        page = (WEB_DIR / "pages" / "nutriparse.html").read_text(encoding="utf-8")
        scripts = SCRIPT_TAG.findall(page)

        self.assertEqual(len(scripts), 1, "Compose should load one entry script, not a classic chain")
        self.assertIn('type="module"', scripts[0])
        self.assertIn('src="/assets/js/nutriparse/boot.js"', scripts[0])

    def test_compose_imports_the_journal_client_module(self):
        journal = (WEB_DIR / "js" / "nutriparse" / "journal.js").read_text(encoding="utf-8")
        store = (WEB_DIR / "js" / "journal-store.js").read_text(encoding="utf-8")

        self.assertIn("from '../journal-store.js'", journal)
        for name in ("read", "addEntries", "updateEntries", "removeEntry", "setGoal", "claimBrowserEntries"):
            self.assertRegex(store, rf"export\s+(?:const|async function|function)\s+{name}\b")

    def test_compose_feature_modules_do_not_reach_for_globals(self):
        modules = [WEB_DIR / "js" / "nutriparse.js", *(WEB_DIR / "js" / "nutriparse").glob("*.js")]
        for module in modules:
            source = module.read_text(encoding="utf-8")
            with self.subTest(module=module.name):
                self.assertNotIn("JournalStore", source)
                self.assertNotIn("window.Config", source)

    def test_food_journal_keeps_the_classic_journal_client(self):
        page = (WEB_DIR / "pages" / "food-journal.html").read_text(encoding="utf-8")
        client = (WEB_DIR / "js" / "journal-client.js").read_text(encoding="utf-8")

        self.assertIn('<script src="/assets/js/journal-client.js"></script>', page)
        self.assertNotIn('<script type="module"', page)
        self.assertNotRegex(client, r"(?m)^\s*export\b")
        self.assertIn("global.JournalStore", client)



if __name__ == "__main__":
    unittest.main()
