#!/usr/bin/env python3
"""Minimal fake Multica CLI for tests. No network, no state."""
import json
import os
import sys


def name():
    args = sys.argv[1:]
    return args[args.index("--name") + 1] if "--name" in args else "x"


def main():
    args = sys.argv[1:]
    s = " ".join(args)
    if os.environ.get("FAKE_LOG"):
        with open(os.environ["FAKE_LOG"], "a", encoding="utf-8") as f:
            f.write(json.dumps(args, ensure_ascii=False) + "\n")
    if "skill list" in s:
        print("[]")
    elif "skill create" in s:
        print(json.dumps({"id": "skill-" + name()}))
    elif "skill update" in s or "skill files upsert" in s:
        print("{}")
    elif "agent list" in s:
        print("[]")
    elif "agent create" in s:
        print(json.dumps({"id": "agent-" + name()}))
    elif "agent update" in s or "agent skills set" in s:
        print("{}")
    elif "squad list" in s:
        print("[]")
    elif "squad create" in s:
        print(json.dumps({"id": "squad-1"}))
    elif "squad member list" in s:
        print("[]")
    elif "squad member add" in s or "squad member set-role" in s or "squad update" in s:
        print("{}")
    else:
        print("{}")


if __name__ == "__main__":
    main()
