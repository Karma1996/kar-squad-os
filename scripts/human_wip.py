#!/usr/bin/env python3
"""Human WIP / SLA check for pending gates (KAR v4.2).

Rules encoded here:
  - Each Decision Owner has at most 2 pending decisions; extra decisions are
    queued by the Lead (active vs queued in the output).
  - A gate pending for >= 24h gets exactly one reminder. After the reminder
    the gate keeps waiting; the script never marks it approved.
  - Only a human can approve a gate; an agent "approval" is reported as a
    violation, never accepted.

The script only reports. The Lead applies it: queue, send the reminder once,
record ``reminder_sent_at`` / ``reminder_count`` in the gate.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from kar_common import (
    HUMAN_SLA_HOURS,
    HUMAN_WIP_LIMIT,
    iter_manifests,
    load_manifest,
    parse_time,
    utcnow,
)


def pending_gates(manifests: list[Path], now) -> tuple[list[dict], list[str]]:
    pending = []
    violations = []
    for path in manifests:
        try:
            manifest = load_manifest(path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            violations.append(f"{path}: unreadable manifest: {exc}")
            continue
        gates = manifest.get("gates")
        if not isinstance(gates, dict):
            continue
        default_owner = manifest.get("decision_owner") or "unassigned"
        issue = manifest.get("issue") or manifest.get("change_set_id")
        for key, gate in gates.items():
            if not isinstance(gate, dict):
                continue
            status = gate.get("status")
            requested = parse_time(gate.get("requested_at"))
            approved = parse_time(gate.get("approved_at"))
            if status == "approved":
                if gate.get("approver_type") != "human":
                    violations.append(
                        f"{issue}/{key}: approved by {gate.get('approver_type')!r}, not human "
                        f"({gate.get('approved_by')!r})"
                    )
                if not gate.get("approved_by"):
                    violations.append(f"{issue}/{key}: approved without approved_by")
                continue
            if status == "rejected":
                continue
            if status not in (None, "pending"):
                violations.append(f"{issue}/{key}: unknown status {status!r}")
                continue
            if requested is None:
                if status == "pending":
                    violations.append(f"{issue}/{key}: pending gate has no valid requested_at")
                continue
            if approved:
                violations.append(f"{issue}/{key}: pending gate has approved_at")
                continue
            owner = gate.get("owner") or gate.get("decision_owner") or default_owner
            reminder_sent = parse_time(gate.get("reminder_sent_at"))
            age_hours = round((now - requested).total_seconds() / 3600, 2)
            pending.append({
                "issue": issue,
                "gate": key,
                "owner": owner,
                "path": str(path),
                "requested_at": requested.isoformat(),
                "age_hours": age_hours,
                "reminder_sent": reminder_sent is not None,
                "reminder_due": age_hours >= HUMAN_SLA_HOURS and reminder_sent is None,
                "sla_hours": HUMAN_SLA_HOURS,
            })
    pending.sort(key=lambda item: (item["requested_at"], str(item["issue"]), item["gate"]))
    return pending, violations


def build_report(manifests: list[str], *, now=None, limit: int = HUMAN_WIP_LIMIT) -> dict:
    now = now or utcnow()
    paths = []
    for root in manifests:
        paths.extend(iter_manifests(Path(root)))
    pending, violations = pending_gates(paths, now)
    by_owner: dict[str, list[dict]] = {}
    for item in pending:
        by_owner.setdefault(str(item["owner"]), []).append(item)
    owners = {}
    for owner, items in sorted(by_owner.items()):
        items.sort(key=lambda item: (item["requested_at"], str(item["issue"]), item["gate"]))
        for index, item in enumerate(items):
            item["queue_state"] = "active" if index < limit else "queued"
        owners[owner] = {
            "pending": len(items),
            "over_limit": max(0, len(items) - limit),
            "active": [item for item in items if item["queue_state"] == "active"],
            "queued": [item for item in items if item["queue_state"] == "queued"],
            "reminders_due": [item for item in items if item["reminder_due"]],
        }
    return {
        "ok": not violations,
        "now": now.isoformat(),
        "limit": limit,
        "sla_hours": HUMAN_SLA_HOURS,
        "owners": owners,
        "totals": {
            "pending": len(pending),
            "owners": len(owners),
            "over_limit": sum(1 for data in owners.values() if data["pending"] > limit),
            "queued": sum(1 for item in pending if item.get("queue_state") == "queued"),
            "reminders_due": sum(1 for item in pending if item["reminder_due"]),
            "after_reminder_waiting": sum(
                1 for item in pending if item["reminder_sent"] and item["age_hours"] >= HUMAN_SLA_HOURS
            ),
        },
        "violations": violations,
    }


def render_markdown(report: dict) -> str:
    lines = [
        f"人类待决策：{report['totals']['pending']} 个 / {report['totals']['owners']} 位 owner；"
        f"上限 {report['limit']}；SLA {report['sla_hours']:.0f}h",
        "",
    ]
    if not report["owners"]:
        lines.append("没有待决策门。")
    for owner, data in report["owners"].items():
        state = f"超限 {data['over_limit']} 个，已排队" if data["over_limit"] else "正常"
        lines.append(f"### {owner} — {data['pending']} 个待决策（{state}）")
        for item in data["active"] + data["queued"]:
            reminder = "；提醒已发，只等人类" if item["reminder_sent"] else (
                "；24h 提醒待发" if item["reminder_due"] else ""
            )
            lines.append(
                f"- {item['issue']}/{item['gate']}：已等 {item['age_hours']:.1f}h"
                f"{'；排队中' if item['queue_state'] == 'queued' else ''}{reminder}"
            )
        lines.append("")
    if report["violations"]:
        lines.append("## 违规")
        lines.extend(f"- {item}" for item in report["violations"])
    return "\n".join(lines).rstrip() + "\n"


def cmd_check(args) -> int:
    now = parse_time(args.now) if args.now else utcnow()
    if now is None:
        raise SystemExit(f"--now is not a valid timestamp: {args.now!r}")
    report = build_report(args.manifests, now=now, limit=args.limit)
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n" if args.json else render_markdown(report)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(text, end="")
    return 1 if report["violations"] else 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="KAR human WIP / SLA check")
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("check", help="Report pending human decisions, queue and reminders")
    p.add_argument("--manifests", action="append", required=True, help="Manifest file or directory (repeatable)")
    p.add_argument("--now", default="", help="Evaluate at this timestamp (default: now, UTC)")
    p.add_argument("--limit", type=int, default=HUMAN_WIP_LIMIT, help="Pending gates per owner (default: 2)")
    p.add_argument("--json", action="store_true")
    p.add_argument("--out", default="", help="Write the report to this path")
    p.set_defaults(func=cmd_check)
    return ap


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
