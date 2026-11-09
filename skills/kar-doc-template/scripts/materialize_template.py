#!/usr/bin/env python3
"""Materialize the squad HTML template into a project's Docs Home.

The template source is the kar-doc-template skill, not the project description.
Falls back to `multica skill files list --with-content` so it works across runtimes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


def run(args: list[str]) -> dict | list:
    proc = subprocess.run(args, text=True, capture_output=True)
    if proc.returncode != 0:
        raise SystemExit(
            f"command failed ({proc.returncode}): {' '.join(args)}\n"
            f"--- stderr ---\n{proc.stderr}\n--- stdout ---\n{proc.stdout}"
        )
    out = (proc.stdout or "").strip()
    if not out:
        return {}
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return {"raw": out}


def as_list(value) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("files", "items", "data"):
            if isinstance(value.get(key), list):
                return value[key]
    return []


def file_path(item: dict) -> str:
    return str(item.get("path") or item.get("name") or "")


def file_content(item: dict) -> str:
    return str(item.get("content") or item.get("body") or "")


def main() -> int:
    ap = argparse.ArgumentParser(description="Materialize kar-doc-template into a Docs Home")
    ap.add_argument("--multica", default=os.environ.get("MULTICA_CLI_PATH") or os.environ.get("MULTICA") or "multica")
    ap.add_argument("--workspace-id", default=os.environ.get("MULTICA_WORKSPACE_ID", ""))
    ap.add_argument("--skill-name", default="kar-doc-template")
    ap.add_argument("--docs-home", required=True, help="Docs Home repo root")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    base = [args.multica]
    if args.workspace_id:
        base += ["--workspace-id", args.workspace_id]

    skills = as_list(run(base + ["skill", "list", "--output", "json"]))
    skill = next((s for s in skills if s.get("name") == args.skill_name), None)
    if not skill:
        raise SystemExit(f"skill not found: {args.skill_name}; run bootstrap.py first")
    skill_id = skill["id"]
    files = as_list(run(base + ["skill", "files", "list", skill_id, "--with-content", "--output", "json"]))
    if not files:
        raise SystemExit(f"no files on skill {args.skill_name}; re-run bootstrap.py --update")

    target_root = Path(args.docs_home) / "multica" / "templates"
    written = []
    for item in files:
        if not isinstance(item, dict):
            continue
        path = file_path(item)
        if not path.startswith("templates/"):
            continue
        rel = Path(path[len("templates/"):])
        if rel.is_absolute() or ".." in rel.parts:
            raise SystemExit(f"unsafe skill file path: {path}")
        dest = target_root / rel
        content = file_content(item)
        if not content:
            raise SystemExit(f"empty content for skill file: {path}")
        written.append((dest, content))
        if not args.dry_run:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8")
            print(f"wrote {dest}")

    if not written:
        raise SystemExit("no templates/ files found on skill; expected templates/KAR-Deliverable-Template.html")

    # Verify version/hash from the materialized template.json.
    meta = next((c for d, c in written if d.name == "template.json"), None)
    html = next((c for d, c in written if d.name.endswith(".html")), None)
    if meta and html:
        try:
            info = json.loads(meta)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"template.json is not valid JSON: {exc}")
        digest = hashlib.sha256(html.encode("utf-8")).hexdigest()
        expected = info.get("sha256", "")
        if expected and digest != expected:
            raise SystemExit(f"template hash mismatch: expected {expected}, got {digest}")
        print(f"template version: {info.get('version')}  squad: {info.get('squad_version')}  sha256: {digest}")
    else:
        print("WARN: template.json or HTML missing from skill files; hash not verified")
    print(f"{'would write' if args.dry_run else 'materialized'} {len(written)} file(s) to {target_root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
