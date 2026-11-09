#!/usr/bin/env python3
"""Merge squad defaults with a project overlay.

Resolution order (low -> high):
  squad.json  <  project description squad-overlay  <  (issue overrides applied by agents)

This script does not probe repositories; the Lead does that with kar-squad-profile.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
DEFAULT_PROFILE = SKILL_DIR / "squad.json"
MARKER_RE = re.compile(r"<!--\s*squad-overlay\s*-->(.*?)<!--\s*/squad-overlay\s*-->", re.DOTALL)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def load_json(path: Path, label: str):
    try:
        return json.loads(read_text(path))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{label} is not valid JSON: {path}: {exc}")


def project_description(args) -> tuple[str, str]:
    if args.description_file:
        p = Path(args.description_file)
        return read_text(p), str(p)
    rp = Path(args.resources_json)
    if rp.exists():
        data = load_json(rp, "resources.json")
        return str(data.get("project_description") or ""), str(rp)
    return "", "(none)"


def extract_overlay(description: str, marker: str) -> tuple[dict, list[str], list[str]]:
    warnings: list[str] = []
    errors: list[str] = []
    match = MARKER_RE.search(description or "")
    if match:
        raw = match.group(1).strip()
        # Allow the JSON to be wrapped in a fenced code block.
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)
        raw = re.sub(r"^~~~(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*~~~$", "", raw)
        try:
            return json.loads(raw.strip()), warnings, errors
        except json.JSONDecodeError as exc:
            errors.append(f"squad-overlay is not valid JSON: {exc}")
            return {}, warnings, errors
    text = (description or "").strip()
    if text.startswith("{"):
        try:
            return json.loads(text), warnings, errors
        except json.JSONDecodeError as exc:
            errors.append(f"project description is not valid JSON: {exc}")
            return {}, warnings, errors
    if text:
        warnings.append(f"no <!-- {marker} --> block found; using squad defaults only")
    else:
        warnings.append("project description is empty; using squad defaults only")
    return {}, warnings, errors


def deep_merge(base, overlay):
    if isinstance(base, dict) and isinstance(overlay, dict):
        out = dict(base)
        for k, v in overlay.items():
            out[k] = deep_merge(out.get(k), v)
        return out
    if isinstance(overlay, list):
        return list(overlay)
    if overlay is None:
        return base
    return overlay


def validate(profile: dict, overlay: dict, effective: dict, allow_empty_repos: bool):
    warnings: list[str] = []
    errors: list[str] = []
    allowed = set(profile.get("allowed_project_fields") or [])
    for key in overlay:
        if allowed and key not in allowed:
            warnings.append(f"unknown project overlay field ignored by contract: {key}")
    allowed_overrides = set(profile.get("allowed_overrides") or [])
    overrides = overlay.get("overrides") or {}
    if isinstance(overrides, dict):
        for key in overrides:
            if allowed_overrides and key not in allowed_overrides:
                warnings.append(f"override not allowed: {key}")
    if isinstance(overrides, dict) and overrides.get("template") == "project":
        if not overrides.get("template_path"):
            errors.append("overrides.template=project requires overrides.template_path")
        else:
            warnings.append("project template override requires explicit human approval before use")

    required = profile.get("required_project_fields") or []
    for field in required:
        value = effective.get(field)
        if field == "repos" and allow_empty_repos:
            continue
        if value in (None, "", [], {}):
            errors.append(f"missing required project fact: {field}")

    repos = effective.get("repos")
    if isinstance(repos, list):
        for i, repo in enumerate(repos):
            if not isinstance(repo, dict):
                errors.append(f"repos[{i}] must be an object")
                continue
            if not repo.get("id"):
                errors.append(f"repos[{i}].id is required")
            if not (repo.get("url") or repo.get("path")):
                warnings.append(f"repos[{i}] has no url/path")
            if not repo.get("test"):
                warnings.append(f"repos[{i}] has no test command; QA/CI cannot be verified automatically")
    elif repos is not None:
        errors.append("repos must be a list")

    if not effective.get("docs_home"):
        warnings.append("docs_home is empty; docs will fall back to the repo docs/ or root multica/")
    return warnings, errors


def main() -> int:
    ap = argparse.ArgumentParser(description="Resolve KAR squad defaults + project overlay")
    ap.add_argument("--squad-profile", default=str(DEFAULT_PROFILE), help="Path to squad.json")
    ap.add_argument("--description-file", default="", help="Project description file; default reads resources.json")
    ap.add_argument("--resources-json", default=".multica/project/resources.json")
    ap.add_argument("--output", default="", help="Write effective config JSON here")
    ap.add_argument("--json", action="store_true", help="Print full JSON")
    ap.add_argument("--allow-empty-repos", action="store_true", help="Only for /init drafts")
    args = ap.parse_args()

    profile_path = Path(args.squad_profile)
    if not profile_path.exists():
        raise SystemExit(f"squad profile not found: {profile_path}")
    profile = load_json(profile_path, "squad profile")
    marker = profile.get("project_overlay_marker", "squad-overlay")
    description, source = project_description(args)
    overlay, warnings, errors = extract_overlay(description, marker)
    overlay_version = overlay.pop("version", None) if isinstance(overlay, dict) else None

    effective = deep_merge(profile, overlay)
    if overlay_version is not None:
        effective["project_overlay_version"] = overlay_version
    v_warnings, v_errors = validate(profile, overlay, effective, args.allow_empty_repos)
    warnings += v_warnings
    errors += v_errors

    result = {
        "effective_config": effective,
        "sources": {"squad_profile": str(profile_path), "project_description": source},
        "warnings": warnings,
        "errors": errors,
    }
    if args.output:
        Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        docs = effective.get("docs", {})
        print("EFFECTIVE CONFIG")
        print(f"  version: {effective.get('version')}")
        print(f"  repos: {len(effective.get('repos') or [])}")
        print(f"  docs_home: {effective.get('docs_home') or '(fallback)'}")
        print(f"  docs.root: {docs.get('root')}")
        print(f"  template: {docs.get('template_skill')} v{docs.get('template_version')} ({docs.get('template_mode')})")
        print(f"  merge_model: {effective.get('overrides', {}).get('merge_model', 'squad-default')}")
        for w in warnings:
            print(f"  WARN: {w}")
        for e in errors:
            print(f"  ERROR: {e}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
