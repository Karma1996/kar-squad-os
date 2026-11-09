#!/usr/bin/env python3
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "skills/kar-squad-profile/scripts/resolve_config.py"


def run(description: str, *extra: str):
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "project.md"
        p.write_text(description, encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--description-file", str(p), "--json", *extra],
            text=True, capture_output=True,
        )
    return proc


class ResolveConfigTest(unittest.TestCase):
    def test_overlay_merge_and_version_separation(self):
        desc = """# Demo
<!-- squad-overlay -->
```json
{
  "version": 1,
  "repos": [{"id":"api","url":"https://example.com/api.git","branch":"develop","test":"npm test"}],
  "docs_home": "/tmp/docs",
  "overrides": {"merge_model":"integration"}
}
```
<!-- /squad-overlay -->
"""
        proc = run(desc)
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        data = json.loads(proc.stdout)
        self.assertEqual(data["effective_config"]["version"], "4.1.0")
        self.assertEqual(data["effective_config"]["project_overlay_version"], 1)
        self.assertEqual(len(data["effective_config"]["repos"]), 1)
        self.assertEqual(data["effective_config"]["docs_home"], "/tmp/docs")
        self.assertEqual(data["effective_config"]["overrides"]["merge_model"], "integration")

    def test_missing_repos_blocks(self):
        desc = """<!-- squad-overlay -->
```json
{"version": 1, "docs_home": "/tmp/docs"}
```
<!-- /squad-overlay -->"""
        proc = run(desc)
        self.assertEqual(proc.returncode, 1)
        data = json.loads(proc.stdout)
        self.assertTrue(any("repos" in e for e in data["errors"]))

    def test_allow_empty_repos_for_init(self):
        desc = """<!-- squad-overlay -->
```json
{"version": 1, "docs_home": "/tmp/docs"}
```
<!-- /squad-overlay -->"""
        proc = run(desc, "--allow-empty-repos")
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)

    def test_unknown_fields_warn(self):
        desc = """<!-- squad-overlay -->
```json
{"version": 1, "repos": [{"id":"api","url":"x","test":"true"}], "unknown": true, "overrides": {"bogus": 1}}
```
<!-- /squad-overlay -->"""
        proc = run(desc)
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        data = json.loads(proc.stdout)
        self.assertTrue(any("unknown" in w for w in data["warnings"]))
        self.assertTrue(any("bogus" in w for w in data["warnings"]))


if __name__ == "__main__":
    unittest.main()
