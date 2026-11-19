#!/usr/bin/env python3
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts/verify_artifact.py"
sys.path.insert(0, str(ROOT / "scripts"))
from verify_artifact import verify_manifest  # noqa: E402


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class VerifyArtifactTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.docs = self.root / "docs"
        self.docs.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def write(self, name: str, text: str):
        path = self.docs / name
        path.write_text(text, encoding="utf-8")
        return path

    def manifest(self, entries: dict) -> Path:
        path = self.docs / "delivery-manifest.json"
        path.write_text(json.dumps({"version": 2, "docs": entries}, ensure_ascii=False), encoding="utf-8")
        return path

    def test_matching_manifest_passes(self):
        text = "<html>requirements</html>"
        self.write("req.html", text)
        path = self.manifest({"requirements": {"path": "req.html", "version": "1.0", "sha": sha(text)}})
        report = verify_manifest(path, self.docs, False)
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["summary"]["total"], 1)

    def test_sha_mismatch_fails(self):
        self.write("req.html", "actual")
        path = self.manifest({"requirements": {"path": "req.html", "sha": "0" * 64}})
        report = verify_manifest(path, self.docs, False)
        self.assertFalse(report["ok"])
        self.assertIn("sha256 mismatch", " ".join(report["errors"]))

    def test_missing_file_fails(self):
        path = self.manifest({"design": {"path": "missing.html", "sha": "0" * 64}})
        report = verify_manifest(path, self.docs, False)
        self.assertFalse(report["ok"])
        self.assertIn("does not exist", " ".join(report["errors"]))

    def test_require_sha_fails_when_missing(self):
        self.write("req.html", "text")
        path = self.manifest({"requirements": {"path": "req.html"}})
        self.assertTrue(verify_manifest(path, self.docs, False)["ok"])
        report = verify_manifest(path, self.docs, True)
        self.assertFalse(report["ok"])
        self.assertIn("required but missing", " ".join(report["errors"]))

    def test_empty_entries_are_skipped(self):
        path = self.manifest({"requirements": {}, "prototype": None})
        report = verify_manifest(path, self.docs, False)
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["summary"]["total"], 0)

    def test_cli_json_and_exit_code(self):
        text = "artifact"
        self.write("req.html", text)
        path = self.manifest({"requirements": {"path": "req.html", "sha": sha(text)}})
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--manifest", str(path), "--json"],
            text=True,
            capture_output=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["ok"])

    def test_single_file_mode(self):
        path = self.docs / "one.html"
        path.write_text("one", encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--file", str(path), "--sha256", sha("one")],
            text=True,
            capture_output=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("VERIFY_ARTIFACT: OK", proc.stdout)


if __name__ == "__main__":
    unittest.main()
