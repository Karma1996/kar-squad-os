#!/usr/bin/env python3
"""Lint a KAR HTML deliverable before it is sent to a human gate.

Checks are intentionally structural and offline:

  python3 scripts/doc_lint.py path/to/需求分析文档.html
  python3 scripts/doc_lint.py --dir <docs-issue-dir> --json
  python3 scripts/doc_lint.py --template-version 4.1 <file...>

It reports ERROR for things that make a document unreviewable (missing summary,
missing evidence/approval sections, unresolved template placeholders, external
assets, broken in-page anchors) and WARN for hygiene issues (TODO text, large
files, missing optional sections). It never rewrites a file.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
PLACEHOLDER_RE = re.compile(r"\{\{[A-Za-z0-9_]+\}\}")
HYGIENE_RE = re.compile(r"\b(TODO|TBD|FIXME|Lorem ipsum)\b", re.IGNORECASE)
EXTERNAL_PREFIXES = ("http://", "https://", "//")


class DocParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: set[str] = set()
        self.hrefs: list[tuple[int, str]] = []
        self.external: list[tuple[int, str]] = []
        self.template_version: str = ""
        self.has_summary = False
        self.summary_text: list[str] = []
        self.summary_depth = 0
        self.sections: set[str] = set()

    def handle_starttag(self, tag: str, attrs) -> None:
        line = self.getpos()[0]
        values = dict(attrs)
        if tag == "html" and values.get("data-template-version"):
            self.template_version = values["data-template-version"]
        element_id = values.get("id")
        if element_id:
            self.ids.add(element_id)
            self.sections.add(element_id)
        if tag == "div" and "summary" in (values.get("class") or "").split():
            self.has_summary = True
            self.summary_depth = 1
        elif self.summary_depth and tag not in VOID_TAGS:
            self.summary_depth += 1
        for attr in ("href", "src"):
            value = values.get(attr)
            if not value:
                continue
            if value.lower().startswith(EXTERNAL_PREFIXES):
                self.external.append((line, value))
            if attr == "href" and value.startswith("#") and len(value) > 1:
                self.hrefs.append((line, value[1:]))

    def handle_startendtag(self, tag: str, attrs) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if self.summary_depth:
            self.summary_depth -= 1

    def handle_data(self, data: str) -> None:
        if self.summary_depth:
            self.summary_text.append(data)


def finding(severity: str, line: int, code: str, message: str) -> dict:
    return {"severity": severity, "line": line, "code": code, "message": message}


def lint_text(text: str, *, template_version: str | None = None, max_bytes: int = 2_000_000, size: int | None = None) -> dict:
    findings: list[dict] = []
    parser = DocParser()
    try:
        parser.feed(text)
        parser.close()
    except Exception as exc:  # HTMLParser is lenient, but never crash a gate on a parse failure.
        findings.append(finding("ERROR", 0, "parse", f"cannot parse HTML: {exc}"))

    if not parser.template_version:
        findings.append(finding("ERROR", 0, "template-version", "missing data-template-version on <html>"))
    elif template_version and parser.template_version != template_version:
        findings.append(
            finding(
                "ERROR",
                0,
                "template-version",
                f"template version {parser.template_version} != expected {template_version}",
            )
        )

    if not parser.has_summary:
        findings.append(finding("ERROR", 0, "summary", "missing summary block (div class=\"summary\")"))
    else:
        summary = " ".join(" ".join(parser.summary_text).split())
        if len(summary) < 20:
            findings.append(finding("ERROR", 0, "summary-empty", "summary is empty or too short"))

    for required in ("evidence", "approval"):
        if required not in parser.sections:
            findings.append(finding("ERROR", 0, f"section-{required}", f"missing <section id=\"{required}\">"))
    for optional in ("provenance", "changelog"):
        if optional not in parser.sections:
            findings.append(finding("WARN", 0, f"section-{optional}", f"missing optional <section id=\"{optional}\">"))

    for match in PLACEHOLDER_RE.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        findings.append(finding("ERROR", line, "placeholder", f"unresolved template placeholder {match.group(0)}"))

    for line, value in parser.external:
        findings.append(finding("ERROR", line, "external-asset", f"external reference is not allowed: {value}"))

    for line, target in parser.hrefs:
        if target not in parser.ids:
            findings.append(finding("ERROR", line, "anchor", f"in-page link #{target} has no matching id"))

    for match in HYGIENE_RE.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        findings.append(finding("WARN", line, "hygiene", f"unfinished marker: {match.group(0)}"))

    actual_size = size if size is not None else len(text.encode("utf-8"))
    if actual_size > max_bytes:
        findings.append(
            finding("WARN", 0, "size", f"file is {actual_size} bytes, above {max_bytes}; consider trimming")
        )

    errors = sum(1 for item in findings if item["severity"] == "ERROR")
    warnings = sum(1 for item in findings if item["severity"] == "WARN")
    return {
        "ok": errors == 0,
        "errors": errors,
        "warnings": warnings,
        "findings": findings,
    }


def lint_file(path: Path, *, template_version: str | None, max_bytes: int) -> dict:
    try:
        data = path.read_bytes()
    except OSError as exc:
        return {
            "ok": False,
            "path": str(path),
            "errors": 1,
            "warnings": 0,
            "findings": [finding("ERROR", 0, "read", str(exc))],
        }
    report = lint_text(data.decode("utf-8", "replace"), template_version=template_version, max_bytes=max_bytes, size=len(data))
    report["path"] = str(path)
    return report


def collect(paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for value in paths:
        path = Path(value)
        if path.is_dir():
            files.extend(sorted(path.glob("*.html")))
        else:
            files.append(path)
    return files


def print_report(report: dict) -> None:
    status = "OK" if report["ok"] else "FAIL"
    print(f"DOC_LINT: {status}  {report.get('path', '')}")
    for item in report["findings"]:
        print(f"  {item['severity']:<5} line {item['line']:<4} {item['code']}: {item['message']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lint KAR HTML deliverables (offline, read-only).")
    parser.add_argument("paths", nargs="*", help="HTML files or directories")
    parser.add_argument("--dir", dest="directory", help="lint every *.html in this directory")
    parser.add_argument("--template-version", default=None, help="require an exact data-template-version")
    parser.add_argument("--max-bytes", type=int, default=2_000_000, help="warn above this size (default 2MB)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    paths = list(args.paths)
    if args.directory:
        paths.append(args.directory)
    files = collect(paths) if paths else []
    if not files:
        print("DOC_LINT: FAIL  no input files", file=sys.stderr)
        return 2

    results = [
        lint_file(path, template_version=args.template_version, max_bytes=args.max_bytes)
        for path in files
    ]
    ok = all(item["ok"] for item in results)
    if args.json:
        print(json.dumps({"ok": ok, "files": results}, ensure_ascii=False, indent=2))
    else:
        for report in results:
            print_report(report)
        total_errors = sum(item["errors"] for item in results)
        total_warnings = sum(item["warnings"] for item in results)
        print(f"  summary: {len(results)} file(s), {total_errors} error(s), {total_warnings} warning(s)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
