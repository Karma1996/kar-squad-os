#!/usr/bin/env python3
"""Generate the KAR catalog files from the single source ``sources/squad.json``.

The hand-maintained JSON files used to be three parallel sources
(``skills.json``, ``agents.json``, ``squad/...json``, plus the squad profile and
``bootstrap.json``), which drifted. v4.4 keeps one source and renders:

  skills.json
  agents.json
  squad/KAR-Delivery-Squad.json
  bootstrap.json
  skills/kar-squad-profile/squad.json

Prose (SKILL.md / agent instructions / docs) stays authored, not generated.

Commands:
  generate.py --check   # fail when a generated file differs from the source
  generate.py --write   # rewrite the generated files
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = Path("sources/squad.json")
TARGETS = (
    "skills.json",
    "agents.json",
    "squad/KAR-Delivery-Squad.json",
    "bootstrap.json",
    "skills/kar-squad-profile/squad.json",
)
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


class SourceError(ValueError):
    pass


def load_source(root: Path) -> dict:
    path = root / SOURCE
    if not path.exists():
        raise SourceError(f"missing single source: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SourceError(f"{path}: invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise SourceError(f"{path}: root must be an object")
    return data


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SourceError(message)


def validate_source(source: dict) -> None:
    kit = source.get("kit")
    _require(isinstance(kit, dict), "kit: required object")
    for key in ("name", "version", "bootstrap_profile", "config", "squad_file", "squad_instructions", "init_template"):
        _require(isinstance(kit.get(key), str) and kit[key].strip(), f"kit.{key}: required non-empty string")
    _require(bool(SEMVER_RE.match(kit["version"])), f"kit.version: expected MAJOR.MINOR.PATCH, got {kit['version']!r}")

    skills = source.get("skills")
    _require(isinstance(skills, list) and skills, "skills: required non-empty list")
    skill_names: set[str] = set()
    for i, skill in enumerate(skills):
        _require(isinstance(skill, dict), f"skills[{i}]: must be an object")
        name = skill.get("name")
        _require(isinstance(name, str) and name, f"skills[{i}].name: required")
        _require(name not in skill_names, f"skills[{i}].name: duplicate {name!r}")
        skill_names.add(name)
        _require(isinstance(skill.get("path"), str) and skill["path"], f"skills[{i}].path: required")
        for j, entry in enumerate(skill.get("files") or []):
            _require(isinstance(entry, dict), f"skills[{i}].files[{j}]: must be an object")
            _require(isinstance(entry.get("source"), str) and entry["source"], f"skills[{i}].files[{j}].source: required")

    agents = source.get("agents")
    _require(isinstance(agents, list) and agents, "agents: required non-empty list")
    agent_names: set[str] = set()
    for i, agent in enumerate(agents):
        _require(isinstance(agent, dict), f"agents[{i}]: must be an object")
        name = agent.get("name")
        _require(isinstance(name, str) and name, f"agents[{i}].name: required")
        _require(name not in agent_names, f"agents[{i}].name: duplicate {name!r}")
        agent_names.add(name)
        bound = agent.get("skills")
        _require(isinstance(bound, list) and bound, f"agents[{i}].skills: required non-empty list")
        for skill in bound:
            _require(skill in skill_names, f"agents[{i}].skills: unknown skill {skill!r}")
        _require(isinstance(agent.get("max"), int) and 1 <= agent["max"] <= 50, f"agents[{i}].max: 1..50")

    squad = source.get("squad")
    _require(isinstance(squad, dict), "squad: required object")
    _require(squad.get("leader") in agent_names, "squad.leader: must be an agent name")
    members = squad.get("members")
    _require(isinstance(members, list) and members, "squad.members: required non-empty list")
    for i, member in enumerate(members):
        _require(isinstance(member, dict), f"squad.members[{i}]: must be an object")
        _require(member.get("name") in agent_names, f"squad.members[{i}].name: not an agent: {member.get('name')!r}")

    defaults = source.get("defaults")
    _require(isinstance(defaults, dict), "defaults: required object")
    for field in ("required_project_fields", "allowed_project_fields", "squad_invariants"):
        _require(isinstance(defaults.get(field), list) and defaults[field], f"defaults.{field}: required non-empty list")


def render(source: dict) -> dict[str, str]:
    """Return path -> canonical file content for every generated file."""
    validate_source(source)
    kit = source["kit"]
    version = kit["version"]
    bootstrap = {
        "name": kit["name"],
        "version": version,
        "profile": kit["bootstrap_profile"],
        "requires": kit.get("requires") or {},
        "skills": "skills.json",
        "agents": "agents.json",
        "squad": kit["squad_file"],
        "config": kit["config"],
        "init_template": kit["init_template"],
        "squad_description": kit.get("squad_description") or "",
        "notes": kit.get("notes") or [],
    }
    profile = {"version": version, **source["defaults"]}
    values = {
        "skills.json": source["skills"],
        "agents.json": source["agents"],
        "squad/KAR-Delivery-Squad.json": source["squad"],
        "bootstrap.json": bootstrap,
        "skills/kar-squad-profile/squad.json": profile,
    }
    return {
        path: json.dumps(values[path], ensure_ascii=False, indent=2) + "\n"
        for path in TARGETS
    }


def check(root: Path) -> tuple[list, list]:
    errors: list[str] = []
    warnings: list[str] = []
    try:
        rendered = render(load_source(root))
    except SourceError as exc:
        return [str(exc)], warnings
    for path, expected in rendered.items():
        target = root / path
        if not target.exists():
            errors.append(f"drift: {path} is missing (run python3 scripts/generate.py --write)")
            continue
        actual = target.read_text(encoding="utf-8")
        if actual != expected:
            errors.append(f"drift: {path} does not match sources/squad.json (run python3 scripts/generate.py --write)")
    return errors, warnings


def write(root: Path) -> list[str]:
    rendered = render(load_source(root))
    written: list[str] = []
    for path, content in rendered.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or target.read_text(encoding="utf-8") != content:
            target.write_text(content, encoding="utf-8")
            written.append(path)
    return written


def cmd_check(args) -> int:
    errors, warnings = check(Path(args.root).resolve())
    if args.json:
        print(json.dumps({"ok": not errors, "errors": errors, "warnings": warnings}, ensure_ascii=False, indent=2))
    elif errors:
        print("GENERATE: FAIL")
        for error in errors:
            print("  ERROR:", error)
    else:
        print(f"GENERATE: OK  source={SOURCE}  files={len(TARGETS)}")
    for warning in warnings:
        print("  WARN:", warning)
    return 1 if errors else 0


def cmd_write(args) -> int:
    root = Path(args.root).resolve()
    try:
        written = write(root)
    except SourceError as exc:
        print("GENERATE: FAIL")
        print("  ERROR:", exc)
        return 1
    if args.json:
        print(json.dumps({"ok": True, "written": written}, ensure_ascii=False, indent=2))
    else:
        print(f"GENERATE: WROTE {len(written)} file(s)")
        for path in written:
            print(f"  {path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Render KAR catalogs from sources/squad.json")
    ap.add_argument("--root", default=str(ROOT), help="Repository root (default: next to scripts/)")
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true", help="Fail when a generated file drifted (default)")
    group.add_argument("--write", action="store_true", help="Rewrite the generated files")
    ap.add_argument("--json", action="store_true")
    return ap


def main() -> int:
    args = build_parser().parse_args()
    return cmd_write(args) if args.write else cmd_check(args)


if __name__ == "__main__":
    sys.exit(main())
