#!/usr/bin/env python3
"""Deterministic queue scheduling for the KAR Lead (v4.4).

The Lead feeds this script a snapshot of running and queued work items and
gets back two decisions:

* preemptions - which running items a queued S0/S1 item displaces;
* dispatch order - the total order in which queued items should start.

Rules (ADR 0002, section 2):

* a queued S0 preempts every running item whose severity is not S0;
* a queued S1 preempts running S2/S3/S4 items on any lane;
* S0 is never preempted, and S1 is never preempted by another S1;
* dispatch order is (severity, program-window priority, enqueued_at, id);
* Quick is strict FIFO; an open Program merge window is the only rule that
  lets a Program item move ahead of a Quick item with the same severity.

Preemption changes execution order only. It never changes gates, acceptance,
human actions, branch/head/write_lock. Only the Python standard library is
used so the script runs in the migration package without dependencies.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from kar_common import iso, parse_time, utcnow

LANES = ("quick", "standard", "program")
SEVERITIES = ("S0", "S1", "S2", "S3", "S4")
SEVERITY_RANK = {severity: rank for rank, severity in enumerate(SEVERITIES)}

# Only queued S0/S1 items may preempt; the value is the set of running
# severities each one displaces.
PREY = {
    "S0": frozenset({"S1", "S2", "S3", "S4"}),
    "S1": frozenset({"S2", "S3", "S4"}),
}


def _nonempty(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _timestamp(value, where: str, errors: list) -> object:
    """Validate one RFC3339 timestamp and return UTC datetime or None."""
    if value is None or value == "":
        errors.append(f"{where}: required RFC3339 timestamp")
        return None
    parsed = parse_time(value)
    if parsed is None:
        errors.append(f"{where}: invalid RFC3339 timestamp")
    return parsed


def _check_id(entry: dict, where: str, seen: dict, errors: list) -> str | None:
    value = entry.get("id")
    if not _nonempty(value):
        errors.append(f"{where}.id: required non-empty string")
        return None
    if value in seen:
        errors.append(f"{where}.id: duplicate id {value} (already used by {seen[value]})")
    else:
        seen[value] = where
    return value


def _entries(data: dict, key: str, errors: list, warnings: list) -> list:
    value = data.get(key)
    if value is None:
        warnings.append(f"{key}: missing; treated as []")
        return []
    if not isinstance(value, list):
        errors.append(f"{key}: expected a list")
        return []
    return value


def validate_queue(data, override_now=None) -> tuple[list, list, dict]:
    """Validate a queue snapshot and return (errors, warnings, model)."""
    errors: list[str] = []
    warnings: list[str] = []
    model = {"now": override_now, "running": [], "queued": []}
    if not isinstance(data, dict):
        errors.append("queue: root must be an object")
        return errors, warnings, model

    if override_now is None:
        if data.get("now") not in (None, ""):
            model["now"] = _timestamp(data.get("now"), "now", errors)
        else:
            model["now"] = utcnow()

    seen: dict[str, str] = {}

    for i, entry in enumerate(_entries(data, "running", errors, warnings)):
        where = f"running[{i}]"
        if not isinstance(entry, dict):
            errors.append(f"{where}: must be an object")
            continue
        lane = entry.get("lane")
        severity = entry.get("severity")
        if lane not in LANES:
            errors.append(f"{where}.lane: expected one of {', '.join(LANES)}")
        if severity not in SEVERITIES:
            errors.append(f"{where}.severity: expected one of {', '.join(SEVERITIES)}")
        model["running"].append({
            "where": where,
            "id": _check_id(entry, where, seen, errors),
            "issue": entry.get("issue") if _nonempty(entry.get("issue")) else None,
            "lane": lane,
            "severity": severity,
            "started_at": _timestamp(entry.get("started_at"), f"{where}.started_at", errors),
        })
        if not _nonempty(entry.get("issue")):
            errors.append(f"{where}.issue: required non-empty string")

    for i, entry in enumerate(_entries(data, "queued", errors, warnings)):
        where = f"queued[{i}]"
        if not isinstance(entry, dict):
            errors.append(f"{where}: must be an object")
            continue
        lane = entry.get("lane")
        severity = entry.get("severity")
        if lane not in LANES:
            errors.append(f"{where}.lane: expected one of {', '.join(LANES)}")
        if severity not in SEVERITIES:
            errors.append(f"{where}.severity: expected one of {', '.join(SEVERITIES)}")
        window = None
        if entry.get("program_merge_window") is not None:
            raw = entry.get("program_merge_window")
            if not isinstance(raw, dict):
                errors.append(
                    f"{where}.program_merge_window: expected an object (open_at/close_at)"
                )
            elif lane != "program":
                errors.append(
                    f"{where}.program_merge_window: only allowed on lane=program"
                )
            else:
                open_at = _timestamp(
                    raw.get("open_at"), f"{where}.program_merge_window.open_at", errors
                )
                close_at = _timestamp(
                    raw.get("close_at"), f"{where}.program_merge_window.close_at", errors
                )
                if open_at is not None and close_at is not None:
                    if close_at <= open_at:
                        errors.append(
                            f"{where}.program_merge_window: close_at must be after open_at"
                        )
                    else:
                        window = {"open_at": open_at, "close_at": close_at}
        model["queued"].append({
            "where": where,
            "id": _check_id(entry, where, seen, errors),
            "issue": entry.get("issue") if _nonempty(entry.get("issue")) else None,
            "lane": lane,
            "severity": severity,
            "enqueued_at": _timestamp(entry.get("enqueued_at"), f"{where}.enqueued_at", errors),
            "window": window,
        })
        if not _nonempty(entry.get("issue")):
            errors.append(f"{where}.issue: required non-empty string")

    return errors, warnings, model


def _window_state(item: dict, now) -> str | None:
    """Return open/closed/future for a Program merge window, else None."""
    window = item.get("window")
    if item.get("lane") != "program" or not window:
        return None
    if window["open_at"] <= now <= window["close_at"]:
        return "open"
    if now > window["close_at"]:
        return "closed"
    return "future"


def _window_priority(state: str | None) -> int:
    return 0 if state == "open" else 1


def _dispatch_reason(item: dict, state: str | None, preempting: set) -> str:
    if item["severity"] == "S0":
        return "S0 抢占"
    if item["id"] in preempting:
        return f"{item['severity']} 抢占"
    if state == "open":
        return (
            "Program 合并窗口开放"
            f"（{item['window']['close_at'].strftime('%H:%M')} 关闭）"
        )
    if item["lane"] == "quick":
        return "Quick FIFO"
    if state == "closed":
        return "窗口已关闭，按入队时间"
    return "同 severity 按入队时间"


def build_plan(model: dict) -> tuple[list, list, list]:
    """Return (dispatch, preemptions, warnings) for a validated model."""
    now = model["now"]
    warnings: list[str] = []
    states: dict[str, str | None] = {}
    for item in model["queued"]:
        state = _window_state(item, now)
        states[item["id"]] = state
        if state == "closed":
            warnings.append(
                f"{item['where']}.program_merge_window: 窗口已关闭，按普通 Program 处理"
            )

    ordered = sorted(
        model["queued"],
        key=lambda item: (
            SEVERITY_RANK[item["severity"]],
            _window_priority(states[item["id"]]),
            item["enqueued_at"],
            item["id"],
        ),
    )

    preemptions: list[dict] = []
    preempting: set[str] = set()
    for running in sorted(model["running"], key=lambda item: item["id"]):
        chosen = None
        for queued in ordered:
            if running["severity"] in PREY.get(queued["severity"], ()):
                chosen = queued
                break
        if chosen is None:
            continue
        preempting.add(chosen["id"])
        reason = (
            "S0 抢占非 S0 运行项"
            if chosen["severity"] == "S0"
            else "S1 抢占 S2–S4 运行项"
        )
        preemptions.append({
            "running_id": running["id"],
            "running_issue": running["issue"],
            "by_queued_id": chosen["id"],
            "reason": reason,
        })

    dispatch = []
    for rank, item in enumerate(ordered, 1):
        dispatch.append({
            "rank": rank,
            "id": item["id"],
            "issue": item["issue"],
            "lane": item["lane"],
            "severity": item["severity"],
            "reason": _dispatch_reason(item, states[item["id"]], preempting),
        })
    return dispatch, preemptions, warnings


def _verdict(report: dict) -> str:
    open_windows = sum(
        1 for item in report["dispatch"] if item["reason"].startswith("Program 合并窗口开放")
    )
    return (
        f"结论：{len(report['dispatch'])} 个排队项；"
        f"{len(report['preemptions'])} 个运行项被抢占；"
        f"{open_windows} 个 Program 合并窗口开放。"
    )


def render_report(report: dict) -> str:
    lines = [f"NOW {report['now']}", "", "派发顺序"]
    dispatch = report["dispatch"]
    if dispatch:
        headers = ["#", "ID", "ISSUE", "LANE", "SEVERITY", "REASON"]
        rows = [
            [str(item["rank"]), str(item["id"]), str(item["issue"]), str(item["lane"]),
             str(item["severity"]), str(item["reason"])]
            for item in dispatch
        ]
        widths = [
            max(len(row[column]) for row in [headers] + rows)
            for column in range(len(headers))
        ]

        def fmt(row: list) -> str:
            cells = [row[column].ljust(widths[column]) for column in range(len(headers) - 1)]
            return "  " + "  ".join(cells + [row[-1]])

        lines.append(fmt(headers))
        lines.extend(fmt(row) for row in rows)
    else:
        lines.append("  （没有排队项）")

    lines += ["", "抢占"]
    preemptions = report["preemptions"]
    if preemptions:
        headers = ["RUNNING", "ISSUE", "BY_QUEUED", "REASON"]
        rows = [
            [str(item["running_id"]), str(item["running_issue"]),
             str(item["by_queued_id"]), str(item["reason"])]
            for item in preemptions
        ]
        widths = [
            max(len(row[column]) for row in [headers] + rows)
            for column in range(len(headers))
        ]

        def fmt(row: list) -> str:
            cells = [row[column].ljust(widths[column]) for column in range(len(headers) - 1)]
            return "  " + "  ".join(cells + [row[-1]])

        lines.append(fmt(headers))
        lines.extend(fmt(row) for row in rows)
    else:
        lines.append("  （无抢占）")

    if report["warnings"]:
        lines.append("")
        lines.extend(f"WARN: {warning}" for warning in report["warnings"])
    lines += ["", _verdict(report)]
    return "\n".join(lines) + "\n"


def _failure_report(now, errors: list, warnings: list) -> dict:
    return {
        "ok": False,
        "now": now,
        "dispatch": [],
        "preemptions": [],
        "errors": errors,
        "warnings": warnings,
    }


def _load(path: str, json_mode: bool):
    """Return (data, error_report). Exactly one side is None."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8")), None
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors = [f"queue: cannot read {path}: {exc}"]
        return None, _failure_report(iso(utcnow()), errors, [])


def _emit_failure(report: dict, json_mode: bool) -> int:
    if json_mode:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("QUEUE: FAIL")
        for error in report["errors"]:
            print("  ERROR:", error)
        for warning in report["warnings"]:
            print("  WARN:", warning)
    return 1


def cmd_check(args) -> int:
    data, failure = _load(args.queue, args.json)
    if failure is not None:
        return _emit_failure(failure, args.json)
    errors, warnings, model = validate_queue(data)
    if args.json:
        print(json.dumps({
            "ok": not errors,
            "errors": errors,
            "warnings": warnings,
        }, ensure_ascii=False, indent=2))
    elif errors:
        print("QUEUE: FAIL")
        for error in errors:
            print("  ERROR:", error)
        for warning in warnings:
            print("  WARN:", warning)
    else:
        print("QUEUE: OK")
        print(f"  running: {len(model['running'])}")
        print(f"  queued: {len(model['queued'])}")
        print(f"  now: {iso(model['now'])}")
        for warning in warnings:
            print("  WARN:", warning)
    return 1 if errors else 0


def cmd_plan(args) -> int:
    override = None
    if args.now:
        override = parse_time(args.now)
        if override is None:
            return _emit_failure(
                _failure_report(iso(utcnow()), [f"--now: invalid RFC3339 timestamp: {args.now!r}"], []),
                args.json,
            )
    data, failure = _load(args.queue, args.json)
    if failure is not None:
        return _emit_failure(failure, args.json)
    errors, warnings, model = validate_queue(data, override)
    if errors:
        now = iso(model["now"]) if model["now"] is not None else iso(utcnow())
        return _emit_failure(_failure_report(now, errors, warnings), args.json)

    dispatch, preemptions, plan_warnings = build_plan(model)
    warnings.extend(plan_warnings)
    report = {
        "ok": True,
        "now": iso(model["now"]),
        "dispatch": dispatch,
        "preemptions": preemptions,
        "errors": [],
        "warnings": warnings,
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_report(report), end="")
    return 0


class _ArgumentParser(argparse.ArgumentParser):
    """argparse exits 2 by default; this CLI promises 1 on usage failure."""

    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


def build_parser() -> argparse.ArgumentParser:
    ap = _ArgumentParser(description="KAR v4.4 deterministic queue scheduler")
    sub = ap.add_subparsers(dest="command", required=True)

    p_check = sub.add_parser("check", help="Validate a queue snapshot (schema only)")
    p_check.add_argument("--queue", required=True, help="Queue JSON file")
    p_check.add_argument("--json", action="store_true")
    p_check.set_defaults(func=cmd_check)

    p_plan = sub.add_parser("plan", help="Validate and compute dispatch order and preemptions")
    p_plan.add_argument("--queue", required=True, help="Queue JSON file")
    p_plan.add_argument("--now", default="", help="Evaluate at this RFC3339 time (overrides file now)")
    p_plan.add_argument("--json", action="store_true")
    p_plan.set_defaults(func=cmd_plan)
    return ap


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
