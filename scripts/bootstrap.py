#!/usr/bin/env python3
"""Create or update the KAR Delivery Squad v4 in a Multica workspace.

Writes: Skills, Agents (skills bindings), Squad and squad member roles.
Does NOT create projects, repos, branch protection, Access, or secrets.

Default is dry-run. Pass --apply to write. Pass --update to update existing
objects; without it, existing Skills/Agents/Squad are left untouched.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip() if (ROOT / "VERSION").exists() else "4.0.0"
BOOTSTRAP = json.loads((ROOT / "bootstrap.json").read_text(encoding="utf-8"))
SKILLS = json.loads((ROOT / "skills.json").read_text(encoding="utf-8"))
AGENTS = json.loads((ROOT / "agents.json").read_text(encoding="utf-8"))
SQUAD = json.loads((ROOT / "squad/KAR-Delivery-Squad.json").read_text(encoding="utf-8"))
SQUAD_INSTRUCTIONS = (ROOT / "squad/KAR-Delivery-Squad.md").read_text(encoding="utf-8")
SQUAD_DESCRIPTION = BOOTSTRAP.get("squad_description") or (
    f"KAR Delivery Squad v{VERSION}：三工作道、候选冻结、审批清单、指标与人类 WIP、"
    "R3 安全 overlay、草稿 checkpoint/steer、接触点预算、低风险 24h 假设、队列抢占、"
    "单一源生成、视觉回归与发布部署自动化。"
)


def run(args: list[str], *, check: bool = True) -> dict | list:
    proc = subprocess.run(args, text=True, capture_output=True)
    if check and proc.returncode != 0:
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


def main() -> int:
    ap = argparse.ArgumentParser(description="KAR Delivery Squad v4 bootstrap")
    ap.add_argument("--multica", default=os.environ.get("MULTICA_CLI_PATH") or os.environ.get("MULTICA") or "multica")
    ap.add_argument("--profile", default=os.environ.get("MULTICA_PROFILE", ""))
    ap.add_argument("--workspace-id", default=os.environ.get("MULTICA_WORKSPACE_ID", ""))
    ap.add_argument("--core-runtime", default=os.environ.get("KAR_CORE_RUNTIME_ID", ""))
    ap.add_argument("--qa-runtime", default=os.environ.get("KAR_QA_RUNTIME_ID", ""))
    ap.add_argument("--apply", action="store_true", help="Actually write. Default is dry-run.")
    ap.add_argument("--dry-run", action="store_true", help="Explicit dry-run (default).")
    ap.add_argument("--update", action="store_true", help="Update existing Skills/Agents/Squad and rebind skills.")
    ap.add_argument("--no-backup", action="store_true", help="Skip pre-apply backup (not recommended).")
    ap.add_argument("--backup-dir", default="backups", help="Backup directory, relative to package root.")
    args = ap.parse_args()

    if args.apply and args.dry_run:
        raise SystemExit("Use either --apply or --dry-run, not both.")
    apply = args.apply
    if not args.workspace_id:
        raise SystemExit("Set --workspace-id or MULTICA_WORKSPACE_ID")
    if not args.core_runtime:
        raise SystemExit("Set --core-runtime or KAR_CORE_RUNTIME_ID")
    qa_runtime = args.qa_runtime or args.core_runtime

    os.chdir(ROOT)
    base = [args.multica]
    if args.profile:
        base += ["--profile", args.profile]
    base += ["--workspace-id", args.workspace_id]

    def fmt_cmd(cmd: list[str]) -> str:
        out: list[str] = []
        skip = False
        for i, arg in enumerate(cmd):
            if skip:
                skip = False
                continue
            if arg in ("--instructions", "--content") and i + 1 < len(cmd):
                out.append(arg)
                out.append(f"<{len(cmd[i + 1])} chars>")
                skip = True
            else:
                out.append(arg)
        return " ".join(out)

    def maybe(cmd: list[str]) -> dict | list:
        if not apply:
            print("DRY-RUN:", fmt_cmd(cmd))
            return {}
        return run(cmd)

    # --- backup ---
    if apply and not args.no_backup:
        bdir = Path(args.backup_dir)
        if not bdir.is_absolute():
            bdir = ROOT / bdir
        bdir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        data = {"version": VERSION, "created_at": datetime.now(timezone.utc).isoformat(), "agents": [], "skills": [], "squad": None, "squad_members": []}
        try:
            for a in as_list(run(base + ["agent", "list", "--output", "json"])):
                data["agents"].append(run(base + ["agent", "get", a["id"], "--output", "json"]))
            for s in as_list(run(base + ["skill", "list", "--output", "json"])):
                detail = run(base + ["skill", "get", s["id"], "--with-content", "--output", "json"])
                if isinstance(detail, dict):
                    detail["files"] = as_list(run(base + ["skill", "files", "list", s["id"], "--with-content", "--output", "json"]))
                data["skills"].append(detail)
            squads = as_list(run(base + ["squad", "list", "--output", "json"]))
            named = by_name(squads)
            if SQUAD["name"] in named:
                sid = named[SQUAD["name"]]["id"]
                data["squad"] = run(base + ["squad", "get", sid, "--output", "json"])
                data["squad_members"] = run(base + ["squad", "member", "list", sid, "--output", "json"])
        except SystemExit as exc:
            raise SystemExit(f"Backup failed; fix the CLI error or pass --no-backup.\n{exc}")
        backup_path = bdir / f"backup-{stamp}.json"
        backup_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"backup written: {backup_path}")

    def upload_skill_files(spec: dict, sid: str) -> None:
        for f in spec.get("files", []) or []:
            src = ROOT / f["source"]
            maybe(base + [
                "skill", "files", "upsert", sid,
                "--path", f["path"],
                "--content-file", str(src),
                "--output", "json",
            ])
            print(("uploaded" if apply else "would upload") + f" file: {spec['name']}/{f['path']}")

    # --- skills ---
    existing_skills = by_name(as_list(run(base + ["skill", "list", "--output", "json"])))
    skill_ids: dict[str, str] = {}
    created = updated = skipped = 0
    for spec in SKILLS:
        name = spec["name"]
        path = ROOT / spec["path"]
        if name in existing_skills:
            sid = existing_skills[name]["id"]
            if args.update:
                maybe(base + ["skill", "update", sid, "--description", spec["description"], "--content-file", str(path), "--output", "json"])
                updated += 1
                print(("updated" if apply else "would update") + f" skill: {name}")
                upload_skill_files(spec, sid)
            else:
                skipped += 1
                print(f"skip skill (exists; use --update): {name}")
            skill_ids[name] = sid
        else:
            res = maybe(base + ["skill", "create", "--name", name, "--description", spec["description"], "--content-file", str(path), "--output", "json"])
            if apply:
                skill_ids[name] = res["id"]
                created += 1
                print(("created" if apply else "would create") + f" skill: {name}")
                upload_skill_files(spec, skill_ids[name])
            else:
                skill_ids[name] = f"dry:{name}"
                created += 1
                upload_skill_files(spec, skill_ids[name])

    # --- agents ---
    existing_agents = by_name(as_list(run(base + ["agent", "list", "--output", "json"])))
    agent_ids: dict[str, str] = {}
    a_created = a_updated = a_skipped = 0
    for spec in AGENTS:
        name = spec["name"]
        instructions = (ROOT / "agents" / f"{name}.md").read_text(encoding="utf-8")
        if name in existing_agents:
            aid = existing_agents[name]["id"]
            if args.update:
                maybe(base + [
                    "agent", "update", aid,
                    "--description", spec["description"],
                    "--instructions", instructions,
                    "--max-concurrent-tasks", str(spec["max"]),
                    "--output", "json",
                ])
                a_updated += 1
                print(("updated" if apply else "would update") + f" agent: {name}")
            else:
                a_skipped += 1
                print(f"skip agent (exists; use --update): {name}")
            agent_ids[name] = aid
        else:
            runtime = args.core_runtime if spec["runtime_env"] == "KAR_CORE_RUNTIME_ID" else qa_runtime
            res = maybe(base + [
                "agent", "create", "--name", name,
                "--runtime-id", runtime,
                "--description", spec["description"],
                "--instructions", instructions,
                "--max-concurrent-tasks", str(spec["max"]),
                "--output", "json",
            ])
            if apply:
                agent_ids[name] = res["id"]
                a_created += 1
                print(("created" if apply else "would create") + f" agent: {name}")
            else:
                agent_ids[name] = f"dry:{name}"
                a_created += 1

    # --- skill bindings ---
    b_set = 0
    for spec in AGENTS:
        name = spec["name"]
        if name not in agent_ids:
            continue
        is_existing = name in existing_agents
        if is_existing and not args.update:
            continue
        ids = [skill_ids[s] for s in spec["skills"] if s in skill_ids]
        missing = [s for s in spec["skills"] if s not in skill_ids]
        if missing:
            raise SystemExit(f"Missing skill ids for {name}: {missing}")
        maybe(base + ["agent", "skills", "set", agent_ids[name], "--skill-ids", ",".join(ids), "--output", "json"])
        b_set += 1
        print(("bound" if apply else "would bind") + f" {len(ids)} skills to {name}")

    # --- squad ---
    squads = by_name(as_list(run(base + ["squad", "list", "--output", "json"])))
    squad_name = SQUAD["name"]
    squad_id = None
    if squad_name in squads:
        squad_id = squads[squad_name]["id"]
        if args.update:
            maybe(base + ["squad", "update", squad_id, "--description", SQUAD_DESCRIPTION, "--instructions", SQUAD_INSTRUCTIONS, "--output", "json"])
            print(("updated" if apply else "would update") + f" squad: {squad_name}")
        else:
            print(f"skip squad (exists; use --update): {squad_name}")
    else:
        res = maybe(base + ["squad", "create", "--name", squad_name, "--description", SQUAD_DESCRIPTION, "--leader", SQUAD["leader"], "--output", "json"])
        if apply:
            squad_id = res["id"]
            print(("created" if apply else "would create") + f" squad: {squad_name}")
        else:
            squad_id = "dry:squad"

    # --- squad members ---
    if squad_id:
        if squad_name in squads and not args.update:
            print("skip squad members (existing squad; use --update)")
            squad_id = None
    if squad_id:
        existing_members = {}
        if squad_id != "dry:squad":
            existing_members = {
                (m.get("member_id"), m.get("member_type")): m
                for m in as_list(run(base + ["squad", "member", "list", squad_id, "--output", "json"]))
            }
        for m in SQUAD["members"]:
            name = m["name"]
            if name == SQUAD["leader"]:
                continue
            if name not in agent_ids:
                print(f"WARN: squad member agent not found: {name}")
                continue
            key = (agent_ids[name], "agent")
            if key in existing_members:
                if args.update:
                    maybe(base + ["squad", "member", "set-role", squad_id, "--member-id", agent_ids[name], "--member-type", "agent", "--role", m["role"], "--output", "json"])
                    print(("updated" if apply else "would update") + f" squad role: {name}")
                continue
            maybe(base + ["squad", "member", "add", squad_id, "--member-id", agent_ids[name], "--type", "agent", "--role", m["role"], "--output", "json"])
            print(("added" if apply else "would add") + f" squad member: {name}")

    mode = "APPLY" if apply else "DRY-RUN"
    print(f"\n{mode} summary: skills created={created} updated={updated} skipped={skipped}; "
          f"agents created={a_created} updated={a_updated} skipped={a_skipped}; bindings={b_set}")
    if not apply:
        print("No changes written. Re-run with --apply to write.")
    else:
        print("Next: python3 scripts/verify.py; then create project/resources, protect branches, configure Access, run /init.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
