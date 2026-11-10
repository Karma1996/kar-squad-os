#!/usr/bin/env python3
"""Audit the v4.4 low-risk 24h default (autonomy) block of a manifest.

``policy.py check`` enforces the same rules inside H3. This script is the fast,
human-readable view for one manifest:

  autonomy.py check    --manifest <path> [--profile h3|draft] [--json]
  autonomy.py deadline --manifest <path> [--json]

Rules (see docs/AUTONOMY.md): only R0/R1 reversible changes with no external
contract, after a project-level human opt-in, may record an assumption once the
H1 card has been pending for at least 24 hours and the single reminder went out.
H1 can still be overridden; H3 is always a human decision.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import timedelta
from pathlib import Path

from kar_common import load_manifest, parse_time
from policy import AUTONOMY_MIN_WINDOW_HOURS, AUTONOMY_RISKS, validate_autonomy


def _block(manifest: dict) -> dict | None:
    block = manifest.get("autonomy")
    return block if isinstance(block, dict) else None


def _deadline(manifest: dict) -> dict | None:
    block = _block(manifest)
    if block is None:
        return None
    wait_started = parse_time(block.get("wait_started_at"))
    window = block.get("window_hours")
    if wait_started is None or not isinstance(window, (int, float)) or isinstance(window, bool):
        return None
    end = wait_started + timedelta(hours=float(window))
    return {
        "wait_started_at": block.get("wait_started_at"),
        "window_hours": window,
        "deadline": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "reminder_at": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "assumed_at": block.get("assumed_at"),
        "state": block.get("state"),
    }


def _eligible(manifest: dict) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    block = _block(manifest) or {}
    risk = str(manifest.get("risk") or "").upper()
    if risk not in AUTONOMY_RISKS:
        reasons.append(f"risk {risk or 'unknown'} is not R0/R1")
    if manifest.get("program_child") is True:
        reasons.append("Program children inherit the parent's gates")
    if block.get("reversible") is not True:
        reasons.append("change is not recorded as reversible")
    if block.get("external_contract") is not False:
        reasons.append("change has (or did not explicitly deny) an external contract")
    opt_in = block.get("project_opt_in")
    if not isinstance(opt_in, dict) or not opt_in.get("by"):
        reasons.append("no project-level human opt-in")
    window = block.get("window_hours")
    if not isinstance(window, (int, float)) or isinstance(window, bool) or window < AUTONOMY_MIN_WINDOW_HOURS:
        reasons.append(f"window_hours is below the {AUTONOMY_MIN_WINDOW_HOURS}h default")
    return not reasons, reasons


def cmd_check(args) -> int:
    manifest = load_manifest(Path(args.manifest))
    errors: list[str] = []
    warnings: list[str] = []
    validate_autonomy(manifest, args.profile == "h3", errors, warnings)
    block = _block(manifest)
    eligible, reasons = _eligible(manifest) if block else (False, [])
    deadline = _deadline(manifest)
    ok = not errors
    if args.json:
        print(json.dumps({
            "ok": ok,
            "used": block is not None,
            "state": (block or {}).get("state"),
            "risk": manifest.get("risk"),
            "eligible": eligible,
            "ineligible_reasons": reasons,
            "deadline": deadline,
            "errors": errors,
            "warnings": warnings,
        }, ensure_ascii=False, indent=2))
    elif block is None:
        print("AUTONOMY: N/A  (no assumption recorded; human gates apply as usual)")
        for warning in warnings:
            print("  WARN:", warning)
    elif errors:
        print("AUTONOMY: FAIL")
        for error in errors:
            print("  ERROR:", error)
        for warning in warnings:
            print("  WARN:", warning)
    else:
        print("AUTONOMY: OK")
        print(f"  risk: {manifest.get('risk')}  state: {block.get('state')}")
        print(f"  eligible: {'yes' if eligible else 'no'}")
        if deadline:
            print(f"  wait: {deadline['wait_started_at']} + {deadline['window_hours']:g}h")
            print(f"  deadline / reminder: {deadline['deadline']}")
            print(f"  assumed_at: {deadline['assumed_at']}")
        print("  H3 still requires a human approval; an assumption never merges the change.")
        for warning in warnings:
            print("  WARN:", warning)
    return 1 if errors else 0


def cmd_deadline(args) -> int:
    manifest = load_manifest(Path(args.manifest))
    block = _block(manifest)
    deadline = _deadline(manifest)
    if block is None:
        message = "autonomy: not used by this manifest"
        if args.json:
            print(json.dumps({"ok": False, "error": message}, ensure_ascii=False, indent=2))
        else:
            print("AUTONOMY: N/A  (no assumption recorded)")
        return 1
    if deadline is None:
        message = "autonomy.wait_started_at / window_hours: invalid or missing"
        if args.json:
            print(json.dumps({"ok": False, "error": message}, ensure_ascii=False, indent=2))
        else:
            print("AUTONOMY: FAIL")
            print("  ERROR:", message)
        return 1
    eligible, reasons = _eligible(manifest)
    payload = {"ok": True, "eligible": eligible, "ineligible_reasons": reasons, **deadline}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("AUTONOMY DEADLINE")
        print(f"  wait started: {deadline['wait_started_at']}  window: {deadline['window_hours']:g}h")
        print(f"  deadline / single reminder: {deadline['deadline']}")
        print(f"  assumed_at: {deadline['assumed_at']}  state: {deadline['state']}")
        print(f"  eligible: {'yes' if eligible else 'no'}")
        for reason in reasons:
            print("  -", reason)
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Audit the KAR v4.4 low-risk 24h autonomy block")
    sub = ap.add_subparsers(dest="command", required=True)
    p_check = sub.add_parser("check", help="Validate autonomy and gate linkage")
    p_check.add_argument("--manifest", required=True)
    p_check.add_argument("--profile", choices=("draft", "h3"), default="h3")
    p_check.add_argument("--json", action="store_true")
    p_check.set_defaults(func=cmd_check)
    p_deadline = sub.add_parser("deadline", help="Print the 24h deadline / reminder time")
    p_deadline.add_argument("--manifest", required=True)
    p_deadline.add_argument("--json", action="store_true")
    p_deadline.set_defaults(func=cmd_deadline)
    return ap


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
