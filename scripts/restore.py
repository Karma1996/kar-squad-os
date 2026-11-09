#!/usr/bin/env python3
"""Restore Skills, Agents and the Squad from a bootstrap backup (KAR v4.2).

``bootstrap.py --apply`` writes ``backups/backup-<stamp>.json`` before it
mutates the workspace. This script replays that snapshot:

  restore.py --backup backups/backup-<stamp>.json --workspace-id <id>

Default is dry-run. Pass --apply to write, then run verify.py and compare.
It restores only Skills, Agents, Squad and agent skill bindings; it never
creates/deletes projects, repos, access rules or secrets, and it never
deletes workspace objects that are absent from the backup.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ONLY_CHOICES = ("skills", "agents", "squad")


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


def by_id(items: list) -> dict:
    return {item["id"]: item for item in items if isinstance(item, dict) and item.get("id")}


def write_temp(directory: Path, name: str, content: str) -> Path:
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description="Restore the KAR squad configuration from a bootstrap backup")
    ap.add_argument("--backup", required=True, help="Path to backup-*.json written by bootstrap.py")
    ap.add_argument("--multica", default=os.environ.get("MULTICA_CLI_PATH") or os.environ.get("MULTICA") or "multica")
    ap.add_argument("--profile", default=os.environ.get("MULTICA_PROFILE", ""))
    ap.add_argument("--workspace-id", default=os.environ.get("MULTICA_WORKSPACE_ID", ""))
    ap.add_argument("--core-runtime", default=os.environ.get("KAR_CORE_RUNTIME_ID", ""))
    ap.add_argument("--qa-runtime", default=os.environ.get("KAR_QA_RUNTIME_ID", ""))
    ap.add_argument("--runtime-map", action="append", default=[], help="agent-name=runtime-id (repeatable)")
    ap.add_argument("--only", action="append", choices=ONLY_CHOICES, default=[], help="Restore only these object types")
    ap.add_argument("--apply", action="store_true", help="Actually write. Default is dry-run.")
    args = ap.parse_args()

    if not args.workspace_id:
        raise SystemExit("Set --workspace-id or MULTICA_WORKSPACE_ID")
    backup_path = Path(args.backup)
    if not backup_path.is_file():
        raise SystemExit(f"backup not found: {backup_path}")
    try:
        backup = json.loads(backup_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"backup is not valid JSON: {exc}")
    if not isinstance(backup, dict):
        raise SystemExit("backup root must be an object")

    only = set(args.only) if args.only else set(ONLY_CHOICES)
    runtime_map = {}
    for value in args.runtime_map:
        if "=" not in value:
            raise SystemExit(f"--runtime-map expects agent-name=runtime-id, got {value!r}")
        name, runtime_id = value.split("=", 1)
        runtime_map[name] = runtime_id

    os.chdir(ROOT)
    base = [args.multica]
    if args.profile:
        base += ["--profile", args.profile]
    base += ["--workspace-id", args.workspace_id]

    def fmt(cmd: list[str]) -> str:
        out = []
        skip = False
        for i, arg in enumerate(cmd):
            if skip:
                skip = False
                continue
            if arg in ("--instructions", "--content") and i + 1 < len(cmd):
                out += [arg, f"<{len(cmd[i + 1])} chars>"]
                skip = True
            else:
                out.append(arg)
        return " ".join(out)

    def maybe(cmd: list[str]) -> dict | list:
        if not args.apply:
            print("DRY-RUN:", fmt(cmd))
            return {}
        return run(cmd)

    print(f"backup: {backup_path}  version={backup.get('version')}  created_at={backup.get('created_at')}  mode={'APPLY' if args.apply else 'DRY-RUN'}")

    existing_skills = by_name(as_list(run(base + ["skill", "list", "--output", "json"])))
    existing_agents = by_name(as_list(run(base + ["agent", "list", "--output", "json"])))
    existing_squads = by_name(as_list(run(base + ["squad", "list", "--output", "json"])))

    skill_id_map: dict[str, str] = {}   # backup id -> restored id
    skill_name_to_new: dict[str, str] = {}
    with tempfile.TemporaryDirectory(prefix="kar-restore-") as tmp:
        tmpdir = Path(tmp)
        if "skills" in only:
            for index, skill in enumerate(backup.get("skills") or []):
                if not isinstance(skill, dict) or not skill.get("name"):
                    continue
                name = skill["name"]
                content_path = write_temp(tmpdir, f"skill-{index}.md", str(skill.get("content") or ""))
                existing = existing_skills.get(name)
                if existing:
                    sid = existing["id"]
                    maybe(base + ["skill", "update", sid, "--description", str(skill.get("description") or ""), "--content-file", str(content_path), "--output", "json"])
                    print(("restored" if args.apply else "would restore") + f" skill: {name}")
                else:
                    res = maybe(base + ["skill", "create", "--name", name, "--description", str(skill.get("description") or ""), "--content-file", str(content_path), "--output", "json"])
                    sid = res.get("id") if args.apply and isinstance(res, dict) else f"dry:{name}"
                    print(("created" if args.apply else "would create") + f" skill: {name}")
                skill_id_map[str(skill.get("id") or name)] = sid
                skill_name_to_new[name] = sid
                for f_index, item in enumerate(skill.get("files") or []):
                    if not isinstance(item, dict) or not item.get("path"):
                        continue
                    file_path = write_temp(tmpdir, f"skill-{index}-file-{f_index}", str(item.get("content") or ""))
                    maybe(base + ["skill", "files", "upsert", sid, "--path", str(item["path"]), "--content-file", str(file_path), "--output", "json"])
                    print(("restored" if args.apply else "would restore") + f" skill file: {name}/{item['path']}")
        else:
            for skill in backup.get("skills") or []:
                if isinstance(skill, dict) and skill.get("name"):
                    existing = existing_skills.get(skill["name"])
                    if existing:
                        skill_name_to_new[skill["name"]] = existing["id"]

        old_agent_to_name = {
            str(agent.get("id")): agent.get("name")
            for agent in backup.get("agents") or []
            if isinstance(agent, dict) and agent.get("id") and agent.get("name")
        }
        agent_id_map: dict[str, str] = {}
        agent_name_to_new: dict[str, str] = {}
        if "agents" in only:
            for index, agent in enumerate(backup.get("agents") or []):
                if not isinstance(agent, dict) or not agent.get("name"):
                    continue
                name = agent["name"]
                instructions = str(agent.get("instructions") or "")
                description = str(agent.get("description") or "")
                max_tasks = int(agent.get("max_concurrent_tasks") or 1)
                existing = existing_agents.get(name)
                if existing:
                    aid = existing["id"]
                    maybe(base + ["agent", "update", aid, "--description", description, "--instructions", instructions, "--max-concurrent-tasks", str(max_tasks), "--output", "json"])
                    print(("restored" if args.apply else "would restore") + f" agent: {name}")
                else:
                    runtime_id = str(agent.get("runtime_id") or runtime_map.get(name) or "")
                    if not runtime_id:
                        runtime_id = args.qa_runtime if name.endswith("QA") else args.core_runtime
                    if not runtime_id:
                        raise SystemExit(
                            f"No runtime for {name}: backup has no runtime_id and --core-runtime/--qa-runtime/--runtime-map is unset"
                        )
                    res = maybe(base + ["agent", "create", "--name", name, "--runtime-id", runtime_id, "--description", description, "--instructions", instructions, "--max-concurrent-tasks", str(max_tasks), "--output", "json"])
                    aid = res.get("id") if args.apply and isinstance(res, dict) else f"dry:{name}"
                    print(("created" if args.apply else "would create") + f" agent: {name}")
                agent_id_map[str(agent.get("id") or name)] = aid
                agent_name_to_new[name] = aid
                bound_names = [s.get("name") for s in (agent.get("skills") or []) if isinstance(s, dict) and s.get("name")]
                bound_ids = [skill_name_to_new[n] for n in bound_names if n in skill_name_to_new]
                missing = [n for n in bound_names if n not in skill_name_to_new]
                if missing:
                    print(f"WARN: skill(s) not restored for {name}: {missing}")
                if bound_ids:
                    maybe(base + ["agent", "skills", "set", aid, "--skill-ids", ",".join(bound_ids), "--output", "json"])
                    print(("bound" if args.apply else "would bind") + f" {len(bound_ids)} skills to {name}")
        else:
            for agent in backup.get("agents") or []:
                if isinstance(agent, dict) and agent.get("name"):
                    existing = existing_agents.get(agent["name"])
                    if existing:
                        agent_name_to_new[agent["name"]] = existing["id"]

        squad = backup.get("squad")
        squad_leader_new = ""
        if "squad" in only and isinstance(squad, dict) and squad.get("name"):
            squad_name = squad["name"]
            leader_old = str(squad.get("leader_id") or "")
            leader_name = old_agent_to_name.get(leader_old) or squad.get("leader") or ""
            leader_id = agent_name_to_new.get(str(leader_name))
            existing = existing_squads.get(squad_name)
            if existing:
                squad_id = existing["id"]
                update_cmd = base + ["squad", "update", squad_id, "--description", str(squad.get("description") or ""), "--instructions", str(squad.get("instructions") or "")]
                if leader_id:
                    update_cmd += ["--leader", leader_id]
                maybe(update_cmd + ["--output", "json"])
                squad_leader_new = leader_id or str(existing.get("leader_id") or "")
                print(("restored" if args.apply else "would restore") + f" squad: {squad_name}")
            else:
                if not leader_id:
                    raise SystemExit(f"Cannot resolve squad leader {leader_name!r} from the backup")
                res = maybe(base + ["squad", "create", "--name", squad_name, "--description", str(squad.get("description") or ""), "--leader", leader_id, "--output", "json"])
                squad_id = res.get("id") if args.apply and isinstance(res, dict) else "dry:squad"
                squad_leader_new = leader_id
                print(("created" if args.apply else "would create") + f" squad: {squad_name}")
            existing_members = {}
            if args.apply:
                existing_members = {
                    (m.get("member_id"), m.get("member_type")): m
                    for m in as_list(run(base + ["squad", "member", "list", squad_id, "--output", "json"]))
                }
            for member in as_list(backup.get("squad_members")):
                if not isinstance(member, dict):
                    continue
                if member.get("member_type") != "agent":
                    print(f"WARN: humans are not restored by this script; re-add {member.get('member_id')} manually")
                    continue
                old_id = str(member.get("member_id") or "")
                new_id = agent_id_map.get(old_id) or agent_name_to_new.get(old_agent_to_name.get(old_id, ""), "")
                if not new_id:
                    print(f"WARN: squad member not in backup agents, skipped: {old_id}")
                    continue
                if new_id == squad_leader_new:
                    continue
                role = str(member.get("role") or "")
                existing_member = existing_members.get((new_id, "agent"))
                if existing_member:
                    maybe(base + ["squad", "member", "set-role", squad_id, "--member-id", new_id, "--member-type", "agent", "--role", role, "--output", "json"])
                    print(("restored" if args.apply else "would restore") + f" squad role: {old_agent_to_name.get(old_id, old_id)}")
                else:
                    maybe(base + ["squad", "member", "add", squad_id, "--member-id", new_id, "--type", "agent", "--role", role, "--output", "json"])
                    print(("added" if args.apply else "would add") + f" squad member: {old_agent_to_name.get(old_id, old_id)}")

    if args.apply:
        print("RESTORE: done. Next: python3 scripts/verify.py")
    else:
        print("RESTORE: dry-run only. Re-run with --apply to restore.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
