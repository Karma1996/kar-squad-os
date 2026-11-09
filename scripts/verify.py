#!/usr/bin/env python3
"""Verify the deployed KAR Delivery Squad v4 matches this package."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = json.loads((ROOT / "skills.json").read_text(encoding="utf-8"))
AGENTS = json.loads((ROOT / "agents.json").read_text(encoding="utf-8"))
SQUAD = json.loads((ROOT / "squad/KAR-Delivery-Squad.json").read_text(encoding="utf-8"))


def normalize(text: str) -> str:
    return (text or "").replace("\r\n", "\n").rstrip()


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
        for key in ("items", "agents", "skills", "squads", "members"):
            if isinstance(value.get(key), list):
                return value[key]
    return []


def by_name(items: list, key: str = "name") -> dict:
    return {item[key]: item for item in items if isinstance(item, dict) and item.get(key)}


def skill_files(base: list[str], skill_id: str) -> dict[str, str]:
    data = run(base + ["skill", "files", "list", skill_id, "--with-content", "--output", "json"])
    files: dict[str, str] = {}
    for item in as_list(data):
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or item.get("name") or "")
        content = str(item.get("content") or item.get("body") or "")
        if path:
            files[path] = content
    return files


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify KAR Delivery Squad v4")
    ap.add_argument("--multica", default=os.environ.get("MULTICA_CLI_PATH") or os.environ.get("MULTICA") or "multica")
    ap.add_argument("--profile", default=os.environ.get("MULTICA_PROFILE", ""))
    ap.add_argument("--workspace-id", default=os.environ.get("MULTICA_WORKSPACE_ID", ""))
    ap.add_argument("--no-content", action="store_true", help="Only check existence, bindings, concurrency, squad.")
    args = ap.parse_args()

    if not args.workspace_id:
        raise SystemExit("Set --workspace-id or MULTICA_WORKSPACE_ID")

    os.chdir(ROOT)
    base = [args.multica]
    if args.profile:
        base += ["--profile", args.profile]
    base += ["--workspace-id", args.workspace_id]

    errors: list[str] = []
    warnings: list[str] = []

    deployed_skills = by_name(as_list(run(base + ["skill", "list", "--output", "json"])))
    skill_ids: dict[str, str] = {}
    for spec in SKILLS:
        name = spec["name"]
        if name not in deployed_skills:
            errors.append(f"missing skill: {name}")
            continue
        sid = deployed_skills[name]["id"]
        skill_ids[name] = sid
        if not args.no_content:
            detail = run(base + ["skill", "get", sid, "--with-content", "--output", "json"])
            expected = (ROOT / spec["path"]).read_text(encoding="utf-8")
            if normalize(detail.get("content", "")) != normalize(expected):
                errors.append(f"skill content differs: {name}")
            deployed_files = skill_files(base, sid)
            for f in spec.get("files", []) or []:
                expected_file = (ROOT / f["source"]).read_text(encoding="utf-8")
                got = deployed_files.get(f["path"])
                if got is None:
                    errors.append(f"skill file missing: {name}/{f['path']}")
                elif normalize(got) != normalize(expected_file):
                    errors.append(f"skill file differs: {name}/{f['path']}")

    if "kar-doc-template" in skill_ids and not args.no_content:
        files = skill_files(base, skill_ids["kar-doc-template"])
        html = files.get("templates/KAR-Deliverable-Template.html")
        meta = files.get("templates/template.json")
        if html and meta:
            try:
                info = json.loads(meta)
                digest = hashlib.sha256(html.encode("utf-8")).hexdigest()
                if info.get("sha256") and info["sha256"] != digest:
                    errors.append("kar-doc-template: template.json sha256 does not match HTML")
                if info.get("version") != "4.1":
                    errors.append(f"kar-doc-template: expected version 4.1, got {info.get('version')}")
            except json.JSONDecodeError:
                errors.append("kar-doc-template: template.json is not valid JSON")
        else:
            errors.append("kar-doc-template: missing template HTML or template.json")

    deployed_agents = by_name(as_list(run(base + ["agent", "list", "--output", "json"])))
    agent_ids: dict[str, str] = {}
    for spec in AGENTS:
        name = spec["name"]
        if name not in deployed_agents:
            errors.append(f"missing agent: {name}")
            continue
        aid = deployed_agents[name]["id"]
        agent_ids[name] = aid
        detail = run(base + ["agent", "get", aid, "--output", "json"])
        if not args.no_content:
            expected = (ROOT / "agents" / f"{name}.md").read_text(encoding="utf-8")
            if normalize(detail.get("instructions", "")) != normalize(expected):
                errors.append(f"agent instructions differ: {name}")
        if int(detail.get("max_concurrent_tasks") or 0) != int(spec["max"]):
            errors.append(f"agent concurrency differs: {name} (expected {spec['max']}, got {detail.get('max_concurrent_tasks')})")
        bound = {s.get("name") for s in (detail.get("skills") or [])}
        expected_bind = set(spec["skills"])
        if bound != expected_bind:
            missing = sorted(expected_bind - bound)
            extra = sorted(bound - expected_bind)
            errors.append(f"agent skill bindings differ: {name}; missing={missing}; extra={extra}")

    squads = by_name(as_list(run(base + ["squad", "list", "--output", "json"])))
    squad_name = SQUAD["name"]
    if squad_name not in squads:
        errors.append(f"missing squad: {squad_name}")
    else:
        squad_id = squads[squad_name]["id"]
        detail = run(base + ["squad", "get", squad_id, "--output", "json"])
        if not args.no_content:
            expected_squad = (ROOT / "squad/KAR-Delivery-Squad.md").read_text(encoding="utf-8")
            if normalize(detail.get("instructions", "")) != normalize(expected_squad):
                errors.append("squad instructions differ")
        leader_id = agent_ids.get(SQUAD["leader"])
        if leader_id and detail.get("leader_id") != leader_id:
            errors.append(f"squad leader differs: expected {SQUAD['leader']} ({leader_id}), got {detail.get('leader_id')}")
        members = as_list(run(base + ["squad", "member", "list", squad_id, "--output", "json"]))
        member_ids = {m.get("member_id") for m in members if m.get("member_type") == "agent"}
        expected_ids = {agent_ids[m["name"]] for m in SQUAD["members"] if m["name"] in agent_ids and m["name"] != SQUAD["leader"]}
        missing = expected_ids - member_ids
        if missing:
            errors.append(f"squad missing members: {sorted(missing)}")
        roles = {m.get("member_id"): m.get("role", "") for m in members if m.get("member_type") == "agent"}
        for m in SQUAD["members"]:
            if m["name"] == SQUAD["leader"] or m["name"] not in agent_ids:
                continue
            got = roles.get(agent_ids[m["name"]], "")
            if got != m["role"]:
                warnings.append(f"squad role differs: {m['name']}")

    if errors:
        print("VERIFY: FAIL")
        for e in errors:
            print("  ERROR:", e)
        for w in warnings:
            print("  WARN:", w)
        return 1

    print("VERIFY: OK")
    print(f"  skills: {len(SKILLS)}")
    print(f"  agents: {len(AGENTS)}")
    print(f"  squad: {SQUAD['name']}")
    for w in warnings:
        print("  WARN:", w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
