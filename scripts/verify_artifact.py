#!/usr/bin/env python3
"""Verify delivery artifacts against a manifest or an explicit digest.

The script is deliberately small and offline:

  python3 scripts/verify_artifact.py --manifest <docs>/delivery-manifest.json
  python3 scripts/verify_artifact.py --manifest <m> --docs-root <docs-home> --require-sha
  python3 scripts/verify_artifact.py --file <path> --sha256 <64-hex> --json

It checks that every recorded document/prototype exists, reports its size and
actual SHA-256, and compares the actual digest with the recorded one. It never
writes files and never calls the network.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

DOC_KEYS = (
    "requirements",
    "prototype",
    "design",
    "test_design",
    "dev_notes",
    "qa_report",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_path(value: str, base: Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (base / path)


def verify_file(name: str, path: Path, expected_sha: str | None, require_sha: bool) -> dict:
    result = {
        "name": name,
        "path": str(path),
        "exists": path.is_file(),
        "size": None,
        "expected_sha": expected_sha or "",
        "actual_sha": "",
        "ok": False,
        "errors": [],
    }
    if not path.is_file():
        result["errors"].append("file does not exist")
        return result
    result["size"] = path.stat().st_size
    result["actual_sha"] = sha256_file(path)
    if expected_sha:
        if result["actual_sha"].lower() != expected_sha.lower():
            result["errors"].append("sha256 mismatch")
    elif require_sha:
        result["errors"].append("sha256 is required but missing from the manifest")
    result["ok"] = not result["errors"]
    return result


def verify_manifest(manifest_path: Path, docs_root: Path | None, require_sha: bool) -> dict:
    errors: list[str] = []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except OSError as exc:
        return {"ok": False, "errors": [f"cannot read manifest: {exc}"], "artifacts": []}
    except json.JSONDecodeError as exc:
        return {"ok": False, "errors": [f"manifest is not valid JSON: {exc}"], "artifacts": []}
    if not isinstance(manifest, dict):
        return {"ok": False, "errors": ["manifest root must be an object"], "artifacts": []}

    base = docs_root or manifest_path.parent
    docs = manifest.get("docs")
    if not isinstance(docs, dict):
        errors.append("manifest.docs must be an object")
        docs = {}

    artifacts: list[dict] = []
    for key in DOC_KEYS:
        entry = docs.get(key)
        if entry is None:
            continue
        if not isinstance(entry, dict):
            errors.append(f"docs.{key} must be an object")
            continue
        if not entry:
            continue
        value = entry.get("path")
        if not value:
            errors.append(f"docs.{key}.path is missing")
            continue
        path = resolve_path(str(value), base)
        result = verify_file(key, path, entry.get("sha"), require_sha)
        artifacts.append(result)
        if not result["ok"]:
            errors.append(f"docs.{key}: " + "; ".join(result["errors"]))

    ok = not errors and all(item["ok"] for item in artifacts)
    return {
        "ok": ok,
        "manifest": str(manifest_path),
        "docs_root": str(base),
        "artifacts": artifacts,
        "summary": {
            "total": len(artifacts),
            "ok": sum(1 for item in artifacts if item["ok"]),
            "failed": sum(1 for item in artifacts if not item["ok"]),
        },
        "errors": errors,
    }


def print_report(report: dict) -> None:
    print(f"VERIFY_ARTIFACT: {'OK' if report.get('ok') else 'FAIL'}")
    if report.get("manifest"):
        print(f"  manifest: {report['manifest']}")
        print(f"  docs_root: {report.get('docs_root', '')}")
    for item in report.get("artifacts", []):
        status = "ok" if item.get("ok") else "FAIL"
        print(
            f"  {item.get('name', '<file>'):<14} {status:<5} "
            f"size={item.get('size')} sha={item.get('actual_sha') or '-'}"
        )
    summary = report.get("summary")
    if summary:
        print(
            f"  summary: {summary['ok']}/{summary['total']} ok, "
            f"{summary['failed']} failed"
        )
    for message in report.get("errors", []):
        if report.get("artifacts"):
            print(f"  ERROR: {message}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify delivery artifacts (offline, read-only)."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--manifest", help="delivery-manifest.json")
    source.add_argument("--file", help="a single artifact file")
    parser.add_argument("--docs-root", help="base directory for relative manifest paths")
    parser.add_argument("--sha256", help="expected SHA-256 for --file")
    parser.add_argument("--require-sha", action="store_true", help="fail when a manifest entry has no sha")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    if args.file:
        path = Path(args.file)
        result = verify_file("file", path, args.sha256, bool(args.sha256))
        report = {
            "ok": result["ok"],
            "artifacts": [result],
            "summary": {
                "total": 1,
                "ok": 1 if result["ok"] else 0,
                "failed": 0 if result["ok"] else 1,
            },
            "errors": [] if result["ok"] else [f"file: {'; '.join(result['errors'])}"],
        }
    else:
        manifest_path = Path(args.manifest)
        docs_root = Path(args.docs_root) if args.docs_root else None
        report = verify_manifest(manifest_path, docs_root, bool(args.require_sha))

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_report(report)
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
