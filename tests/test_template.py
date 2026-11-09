#!/usr/bin/env python3
import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class TemplateTest(unittest.TestCase):
    def test_version_hash_and_slots(self):
        tpl_dir = ROOT / "skills/kar-doc-template/templates"
        html = (tpl_dir / "KAR-Deliverable-Template.html").read_bytes()
        info = json.loads((tpl_dir / "template.json").read_text(encoding="utf-8"))
        self.assertEqual(info["version"], "4.1")
        self.assertEqual(info["squad_version"], "4.1.0")
        self.assertEqual(info["sha256"], hashlib.sha256(html).hexdigest())
        self.assertTrue(info["slots"])
        self.assertIn('data-template-version="4.1"', html.decode("utf-8"))

    def test_no_cdn(self):
        html = (ROOT / "skills/kar-doc-template/templates/KAR-Deliverable-Template.html").read_text(encoding="utf-8")
        self.assertNotIn("cdn.", html.lower())
        self.assertNotIn("https://", html.lower())


if __name__ == "__main__":
    unittest.main()
