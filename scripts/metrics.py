#!/usr/bin/env python3
"""Per-issue metrics and the weekly 6-metric summary (KAR v4.2).

Reads every delivery-manifest.json under the given roots and reports:
  - the 5 per-issue metrics: human_touches, wait_human, rework_rounds,
    candidate_recuts, escaped_defects;
  - cycle_time_hours as the sixth weekly metric;
  - an ISO-week summary, plus the 2-week baseline status.

Nothing is inferred silently: an issue with a missing metric is listed as
incomplete and makes --strict fail.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from kar_common import (
    METRIC_KEYS,
    iter_manifests,
    load_manifest,
    normalize_number,
    parse_time,
)


def iso_week(dt) -> str:
    year, week, _ = dt.isocalendar()
    return f"{year}-W{week:02d}"


def collect(paths: list[Path]) -> dict:
    per_issue = []
    incomplete = []
    for path in paths:
        try:
            manifest = load_manifest(path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            incomplete.append({"path": str(path), "issue": None, "missing": ["unreadable"], "error": str(exc)})
            continue
        metrics = manifest.get("metrics")
        metrics = metrics if isinstance(metrics, dict) else {}
        values = {}
        missing = []
        for key in METRIC_KEYS:
            number = normalize_number(metrics.get(key))
            values[key] = number
            if number is None:
                missing.append(key)
        gates = manifest.get("gates") if isinstance(manifest.get("gates"), dict) else {}
        h1 = parse_time((gates.get("h1") or {}).get("requested_at")) if isinstance(gates.get("h1"), dict) else None
        h3 = parse_time((gates.get("h3") or {}).get("approved_at")) if isinstance(gates.get("h3"), dict) else None
        cycle = normalize_number(metrics.get("cycle_time_hours"))
        if cycle is None and h1 and h3 and h3 >= h1:
            cycle = round((h3 - h1).total_seconds() / 3600, 2)
        closed = parse_time(metrics.get("closed_at")) or h3
        entry = {
            "issue": manifest.get("issue") or manifest.get("change_set_id"),
            "path": str(path),
            "week": iso_week(closed) if closed else None,
            "closed_at": closed.isoformat() if closed else None,
            "metrics": dict(values),
            "cycle_time_hours": cycle,
            "missing": missing,
        }
        per_issue.append(entry)
        if missing:
            incomplete.append({"path": str(path), "issue": entry["issue"], "missing": missing})
    per_issue.sort(key=lambda item: (item["week"] or "9999", str(item["issue"])))
    return {
        "per_issue": per_issue,
        "incomplete": incomplete,
        "complete": [item for item in per_issue if not item["missing"]],
    }


def aggregate(complete: list[dict], weeks: int) -> tuple[list[dict], dict]:
    buckets: dict[str, list[dict]] = {}
    unclosed = []
    for item in complete:
        if item["week"] is None:
            unclosed.append(item["issue"])
        else:
            buckets.setdefault(item["week"], []).append(item)
    rows = []
    for week in sorted(buckets):
        items = buckets[week]
        row = {"week": week, "issues": len(items)}
        for key in METRIC_KEYS:
            total = sum(float(item["metrics"][key]) for item in items)
            row[key] = round(total, 2)
        wait = sum(float(item["metrics"]["wait_human"]) for item in items)
        row["wait_human"] = round(wait / len(items), 2)
        cycles = [item["cycle_time_hours"] for item in items if item["cycle_time_hours"] is not None]
        row["cycle_time_hours"] = round(sum(cycles) / len(cycles), 2) if cycles else None
        rows.append(row)
    baseline = {
        "weeks_required": weeks,
        "weeks_collected": len(rows),
        "ready": len(rows) >= weeks,
        "unclosed": unclosed,
    }
    return rows, baseline


def render_markdown(report: dict) -> str:
    lines = ["## 每 issue 指标", ""]
    lines.append("| issue | human_touches | wait_human(h) | rework_rounds | candidate_recuts | escaped_defects | cycle_time(h) | week |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |")
    for item in report["per_issue"]:
        m = item["metrics"]

        def show(value):
            return "—" if value is None else value

        lines.append(
            f"| {item['issue']} | {show(m['human_touches'])} | {show(m['wait_human'])} | "
            f"{show(m['rework_rounds'])} | {show(m['candidate_recuts'])} | "
            f"{show(m['escaped_defects'])} | {show(item['cycle_time_hours'])} | {item['week'] or '未关闭'} |"
        )
    lines += ["", "## 每周 6 指标", ""]
    lines.append("| week | issues | human_touches | wait_human(h, avg) | rework_rounds | candidate_recuts | escaped_defects | cycle_time(h, avg) |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for row in report["weeks"]:
        lines.append(
            f"| {row['week']} | {row['issues']} | {row['human_touches']} | {row['wait_human']} | "
            f"{row['rework_rounds']} | {row['candidate_recuts']} | {row['escaped_defects']} | "
            f"{row['cycle_time_hours'] if row['cycle_time_hours'] is not None else '—'} |"
        )
    baseline = report["baseline"]
    lines += ["", f"基线段：已采集 {baseline['weeks_collected']}/{baseline['weeks_required']} 周"
              f"{'，可以开始对比' if baseline['ready'] else '，继续采集，先不优化'}。"]
    if baseline["unclosed"]:
        lines.append(f"未关闭 issue（缺 closed_at / H3 时间，未计入周汇总）：{', '.join(map(str, baseline['unclosed']))}")
    if report["incomplete"]:
        lines += ["", "## 指标缺失", ""]
        for item in report["incomplete"]:
            lines.append(f"- {item.get('issue') or item.get('path')}: missing {', '.join(item['missing'])}")
    return "\n".join(lines) + "\n"


def build_report(manifests: list[str], *, week: str = "", baseline_weeks: int = 2) -> dict:
    paths = []
    for root in manifests:
        paths.extend(iter_manifests(Path(root)))
    collected = collect(paths)
    rows, baseline = aggregate(collected["complete"], baseline_weeks)
    all_rows = rows
    if week:
        rows = [row for row in rows if row["week"] == week]
        baseline = dict(baseline, filtered_week=week, weeks_collected=len(rows))
    return {
        "per_issue": collected["per_issue"],
        "incomplete": collected["incomplete"],
        "weeks": rows,
        "all_weeks": all_rows,
        "baseline": baseline,
    }


def cmd_report(args) -> int:
    report = build_report(args.manifests, week=args.week, baseline_weeks=args.baseline_weeks)
    text = (
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.format == "json"
        else render_markdown(report)
    )
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(text, end="")
    if args.strict and report["incomplete"]:
        print(f"METRICS: FAIL — {len(report['incomplete'])} manifest(s) missing metrics", file=sys.stderr)
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="KAR per-issue and weekly metrics")
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("report", help="Report per-issue metrics and weekly summary")
    p.add_argument("--manifests", action="append", required=True, help="Manifest file or directory (repeatable)")
    p.add_argument("--week", default="", help="Only show one ISO week, e.g. 2026-W45")
    p.add_argument("--baseline-weeks", type=int, default=2, help="Weeks of baseline required (default: 2)")
    p.add_argument("--format", choices=("markdown", "json"), default="markdown")
    p.add_argument("--out", default="", help="Write the report to this path")
    p.add_argument("--strict", action="store_true", help="Exit 1 when a manifest is missing metrics")
    p.set_defaults(func=cmd_report)
    return ap


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
