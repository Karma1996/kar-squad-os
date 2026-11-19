#!/usr/bin/env python3
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts/doc_lint.py"
sys.path.insert(0, str(ROOT / "scripts"))
from doc_lint import lint_text  # noqa: E402

VALID = """<!doctype html>
<html lang="zh-CN" data-template-version="4.1">
<head><title>需求基线</title></head>
<body>
<div class="summary"><strong>一页摘要</strong><p>这是至少二十个字符的摘要内容，用来通过最小长度检查。</p></div>
<main><h2>正文</h2><p>内容</p><a href="#evidence">证据</a></main>
<section id="evidence"><h2>证据</h2></section>
<section id="approval"><h2>批准</h2></section>
<section id="provenance"><h2>来源</h2></section>
<section id="changelog"><h2>变更</h2></section>
</body></html>"""


class DocLintTest(unittest.TestCase):
    def test_valid_document_passes(self):
        report = lint_text(VALID)
        self.assertTrue(report["ok"], report["findings"])

    def test_missing_summary_fails(self):
        broken = VALID.replace('<div class="summary">', '<div class="other">')
        report = lint_text(broken)
        self.assertFalse(report["ok"])
        self.assertIn("summary", {f["code"] for f in report["findings"]})

    def test_placeholder_fails(self):
        report = lint_text(VALID.replace("<p>内容</p>", "<p>{{BODY}}</p>"))
        self.assertFalse(report["ok"])
        self.assertIn("placeholder", {f["code"] for f in report["findings"]})

    def test_external_asset_fails(self):
        report = lint_text(VALID.replace("</main>", '<img src="https://cdn.example/x.png"></main>'))
        self.assertFalse(report["ok"])
        self.assertIn("external-asset", {f["code"] for f in report["findings"]})

    def test_broken_anchor_fails(self):
        report = lint_text(VALID.replace('href="#evidence"', 'href="#missing"'))
        self.assertFalse(report["ok"])
        self.assertIn("anchor", {f["code"] for f in report["findings"]})

    def test_missing_template_version_fails(self):
        report = lint_text(VALID.replace(' data-template-version="4.1"', ""))
        self.assertFalse(report["ok"])
        self.assertIn("template-version", {f["code"] for f in report["findings"]})

    def test_todo_is_warning_only(self):
        report = lint_text(VALID.replace("<p>内容</p>", "<p>TODO 补充</p>"))
        self.assertTrue(report["ok"], report["findings"])
        self.assertTrue(any(f["severity"] == "WARN" and f["code"] == "hygiene" for f in report["findings"]))

    def test_cli_directory_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "doc.html"
            path.write_text(VALID, encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(SCRIPT), "--dir", tmp, "--json"],
                text=True,
                capture_output=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertTrue(payload["ok"])
            self.assertEqual(len(payload["files"]), 1)

    def test_cli_invalid_exit_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "doc.html"
            path.write_text(VALID.replace("<p>内容</p>", "<p>{{BODY}}</p>"), encoding="utf-8")
            proc = subprocess.run([sys.executable, str(SCRIPT), str(path)], text=True, capture_output=True)
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            self.assertIn("DOC_LINT: FAIL", proc.stdout)


if __name__ == "__main__":
    unittest.main()
