#!/usr/bin/env python3
"""Minimal fake Multica CLI for tests.

By default every list is empty and every write returns a made-up id, which is
enough to test create paths. To test update paths, point FAKE_STATE at a JSON
file with any of: skills, skill_details, skill_files, agents, agent_details,
squads, squad_details, squad_members. Calls are appended to FAKE_LOG.
"""
import json
import os
import sys


def load_state():
    path = os.environ.get("FAKE_STATE")
    if not path or not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


STATE = load_state()


def name():
    args = sys.argv[1:]
    return args[args.index("--name") + 1] if "--name" in args else "x"


def arg_after(prefix):
    args = sys.argv[1:]
    for i in range(len(args) - len(prefix) + 1):
        if args[i:i + len(prefix)] == prefix and i + len(prefix) < len(args):
            return args[i + len(prefix)]
    return ""


def find(items, item_id):
    for item in items:
        if isinstance(item, dict) and item.get("id") == item_id:
            return item
    return {}


def main():
    args = sys.argv[1:]
    s = " ".join(args)
    if os.environ.get("FAKE_LOG"):
        with open(os.environ["FAKE_LOG"], "a", encoding="utf-8") as f:
            f.write(json.dumps(args, ensure_ascii=False) + "\n")
    if "skill files list" in s:
        sid = arg_after(["skill", "files", "list"])
        print(json.dumps(STATE.get("skill_files", {}).get(sid, [])))
    elif "skill files upsert" in s:
        print("{}")
    elif "skill list" in s:
        print(json.dumps(STATE.get("skills", [])))
    elif "skill get" in s:
        sid = arg_after(["skill", "get"])
        detail = STATE.get("skill_details", {}).get(sid) or find(STATE.get("skills", []), sid)
        print(json.dumps(detail))
    elif "skill create" in s:
        print(json.dumps({"id": "skill-" + name()}))
    elif "skill update" in s:
        print("{}")
    elif "agent list" in s:
        print(json.dumps(STATE.get("agents", [])))
    elif "agent get" in s:
        aid = arg_after(["agent", "get"])
        detail = STATE.get("agent_details", {}).get(aid) or find(STATE.get("agents", []), aid)
        print(json.dumps(detail))
    elif "agent create" in s:
        print(json.dumps({"id": "agent-" + name()}))
    elif "agent update" in s or "agent skills set" in s:
        print("{}")
    elif "squad list" in s:
        print(json.dumps(STATE.get("squads", [])))
    elif "squad get" in s:
        sid = arg_after(["squad", "get"])
        detail = STATE.get("squad_details", {}).get(sid) or find(STATE.get("squads", []), sid)
        print(json.dumps(detail))
    elif "squad create" in s:
        print(json.dumps({"id": "squad-1"}))
    elif "squad member list" in s:
        print(json.dumps(STATE.get("squad_members", [])))
    elif "squad member add" in s or "squad member set-role" in s or "squad update" in s:
        print("{}")
    else:
        print("{}")


if __name__ == "__main__":
    main()
