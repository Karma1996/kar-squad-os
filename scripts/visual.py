#!/usr/bin/env python3
"""v4.4 visual regression adapter.

No browser or image library is bundled. The project declares its own tool and
command in ``visual.json``; this script only:

* ``init``    writes a project facts template;
* ``check``   validates the config/results pair, coverage and thresholds;
* ``capture`` runs the declared command once per screen x breakpoint x theme
              and aggregates the JSON objects it prints.

Only the Python standard library is used. A missing combination, a duplicate,
an unavailable tool or an unparseable command is an explicit failure -- never
a silent PASS.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

RFC3339_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})$"
)
HEX8_RE = re.compile(r"^[0-9a-fA-F]{8,}$")
MISSING = object()
ERROR_DETAIL_LIMIT = 240

INIT_CONFIG = {
    "version": 1,
    "tool": "playwright",
    "command": ["node", "visual/compare.mjs"],
    "breakpoints": [
        {"name": "mobile", "width": 375},
        {"name": "tablet", "width": 768},
        {"name": "desktop", "width": 1440},
    ],
    "themes": ["light"],
    "thresholds": {"max_diff_ratio": 0.005, "critical_max_diff_ratio": 0.0},
    "screens": [{"id": "SC-01-home", "url": "/"}],
}


# --- small helpers ---------------------------------------------------------


def _nonempty(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_number(value) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, ValueError):
        return False


def _is_ratio(value) -> bool:
    return _is_number(value) and 0 <= value <= 1


def _num(value) -> str:
    """Render a number without losing the ``0.0`` distinction in messages."""
    if isinstance(value, float):
        return repr(value)
    return str(value)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_rfc3339(value) -> datetime | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not RFC3339_RE.match(text):
        return None
    normalized = text.replace("t", "T", 1)
    if normalized.endswith(("Z", "z")):
        normalized = normalized[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _read_json(path, label: str) -> tuple[dict | None, str | None]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        return None, f"{label}: cannot read {path}: {exc}"
    except json.JSONDecodeError as exc:
        return None, f"{label}: invalid JSON in {path}: {exc}"
    return data, None


def _write_json(path, data: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=2)
    path.write_text(text + "\n", encoding="utf-8")


def _truncate(text: str, limit: int = ERROR_DETAIL_LIMIT) -> str:
    compact = " ".join(str(text).split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."


def _key(combo: tuple) -> str:
    screen, breakpoint, theme = combo
    return f"{screen}/{breakpoint}/{theme}"


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


# --- config validation -----------------------------------------------------


def validate_config(config) -> tuple[list[str], list[str]]:
    """Return (errors, warnings) for a project visual.json."""
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(config, dict):
        return ["config: root must be a JSON object"], warnings

    version = config.get("version")
    if version is not None and (isinstance(version, bool) or version != 1):
        errors.append("version: expected 1")

    if not _nonempty(config.get("tool")):
        errors.append("tool: non-empty string required")

    command = config.get("command")
    if command is not None:
        if not isinstance(command, list):
            errors.append("command: expected a list of strings")
        else:
            for i, item in enumerate(command):
                if not _nonempty(item):
                    errors.append(f"command[{i}]: non-empty string required")

    breakpoints = config.get("breakpoints")
    if not isinstance(breakpoints, list) or not breakpoints:
        errors.append("breakpoints: non-empty list required")
    else:
        names: set[str] = set()
        for i, breakpoint in enumerate(breakpoints):
            where = f"breakpoints[{i}]"
            if not isinstance(breakpoint, dict):
                errors.append(f"{where}: must be an object")
                continue
            name = breakpoint.get("name")
            if not _nonempty(name):
                errors.append(f"{where}.name: non-empty string required")
            elif name in names:
                errors.append(f"{where}.name: duplicate breakpoint name {name!r}")
            else:
                names.add(name)
            width = breakpoint.get("width")
            if isinstance(width, bool) or not isinstance(width, int) or width <= 0:
                errors.append(f"{where}.width: positive integer required")

    themes = config.get("themes")
    if not isinstance(themes, list) or not themes:
        errors.append("themes: non-empty list required")
    else:
        seen_themes: set[str] = set()
        for i, theme in enumerate(themes):
            if not _nonempty(theme):
                errors.append(f"themes[{i}]: non-empty string required")
            elif theme in seen_themes:
                errors.append(f"themes[{i}]: duplicate theme {theme!r}")
            else:
                seen_themes.add(theme)

    thresholds = config.get("thresholds")
    if not isinstance(thresholds, dict):
        errors.append("thresholds: object required (max_diff_ratio)")
    else:
        max_diff = thresholds.get("max_diff_ratio", MISSING)
        critical_diff = thresholds.get("critical_max_diff_ratio", 0.0)
        max_ok = max_diff is not MISSING and _is_ratio(max_diff)
        critical_ok = _is_ratio(critical_diff)
        if max_diff is MISSING:
            errors.append("thresholds.max_diff_ratio: required number in [0, 1]")
        elif not max_ok:
            errors.append("thresholds.max_diff_ratio: number in [0, 1] required")
        if not critical_ok:
            errors.append("thresholds.critical_max_diff_ratio: number in [0, 1] required")
        if max_ok and critical_ok and critical_diff > max_diff:
            errors.append("thresholds.critical_max_diff_ratio: must be <= max_diff_ratio")

    screens = config.get("screens")
    screen_ids: set[str] = set()
    if not isinstance(screens, list) or not screens:
        errors.append("screens: non-empty list required")
    else:
        for i, screen in enumerate(screens):
            where = f"screens[{i}]"
            if not isinstance(screen, dict):
                errors.append(f"{where}: must be an object")
                continue
            screen_id = screen.get("id")
            if not _nonempty(screen_id):
                errors.append(f"{where}.id: non-empty string required")
            elif screen_id in screen_ids:
                errors.append(f"{where}.id: duplicate screen id {screen_id!r}")
            else:
                screen_ids.add(screen_id)
            if "url" in screen and not _nonempty(screen.get("url")):
                errors.append(f"{where}.url: non-empty string required when set")
            if "critical" in screen and not isinstance(screen.get("critical"), bool):
                errors.append(f"{where}.critical: expected true or false")

    critical_screens = config.get("critical_screens")
    if critical_screens is not None:
        if not isinstance(critical_screens, list):
            errors.append("critical_screens: expected a list of screen ids")
        else:
            seen_critical: set[str] = set()
            for i, screen_id in enumerate(critical_screens):
                if not _nonempty(screen_id):
                    errors.append(f"critical_screens[{i}]: non-empty screen id required")
                    continue
                if screen_id in seen_critical:
                    warnings.append(
                        f"critical_screens[{i}]: duplicate screen id {screen_id!r}"
                    )
                else:
                    seen_critical.add(screen_id)
                if screen_id not in screen_ids:
                    errors.append(
                        f"critical_screens[{i}]: unknown screen {screen_id!r} "
                        "(must be a subset of screens)"
                    )

    return errors, warnings


def _facts(config: dict) -> dict:
    """Validated config as lookup tables; call only after validate_config()."""
    screens = config["screens"]
    critical = {screen["id"] for screen in screens if screen.get("critical") is True}
    critical.update(config.get("critical_screens") or [])
    return {
        "tool": config["tool"],
        "command": config.get("command"),
        "breakpoints": config["breakpoints"],
        "themes": config["themes"],
        "screens": screens,
        "screen_ids": {screen["id"] for screen in screens},
        "breakpoint_names": {item["name"] for item in config["breakpoints"]},
        "theme_names": set(config["themes"]),
        "critical_ids": critical,
        "max_diff_ratio": config["thresholds"]["max_diff_ratio"],
        "critical_max_diff_ratio": config["thresholds"].get(
            "critical_max_diff_ratio", 0.0
        ),
    }


def _combinations(facts: dict) -> list[tuple[dict, dict, str]]:
    return [
        (screen, breakpoint, theme)
        for screen in facts["screens"]
        for breakpoint in facts["breakpoints"]
        for theme in facts["themes"]
    ]


# --- result validation -----------------------------------------------------


def _empty_coverage(missing: list[str] | None = None) -> dict:
    missing = list(missing or [])
    return {
        "expected": len(missing),
        "covered": 0,
        "missing": missing,
        "duplicates": [],
    }


def _report(tool, coverage: dict, failures, warnings, errors) -> dict:
    return {
        "ok": not failures and not errors,
        "tool": tool,
        "coverage": coverage,
        "failures": list(failures),
        "warnings": list(warnings),
        "errors": list(errors),
    }


def assess_results(config: dict, results) -> dict:
    """Validate a results object against the config and enforce thresholds."""
    facts = _facts(config)
    expected = _combinations(facts)
    expected_keys = {
        (screen["id"], breakpoint["name"], theme)
        for screen, breakpoint, theme in expected
    }
    errors: list[str] = []
    failures: list[str] = []
    warnings: list[str] = []
    coverage = _empty_coverage(
        [_key((screen["id"], breakpoint["name"], theme)) for screen, breakpoint, theme in expected]
    )

    if not isinstance(results, dict):
        errors.append("results: root must be a JSON object")
        return _report(facts["tool"], coverage, failures, warnings, errors)

    version = results.get("version")
    if version is not None and (isinstance(version, bool) or version != 1):
        errors.append("results.version: expected 1")

    result_tool = results.get("tool")
    if result_tool != facts["tool"]:
        errors.append(
            f"tool: results tool {result_tool!r} does not match config tool "
            f"{facts['tool']!r}"
        )

    if _parse_rfc3339(results.get("generated_at")) is None:
        errors.append(
            "generated_at: valid RFC3339 timestamp required "
            "(for example 2026-11-05T08:00:00Z)"
        )

    if results.get("tool_available") is not True:
        errors.append("tool_available: 工具不可用，不能判定通过（BLOCKED）")

    entries = results.get("screens")
    if not isinstance(entries, list):
        errors.append("screens: list of result objects required")
        entries = []

    covered: set[tuple] = set()
    duplicates: list[str] = []
    for i, entry in enumerate(entries):
        where = f"screens[{i}]"
        if not isinstance(entry, dict):
            errors.append(f"{where}: must be an object")
            continue

        screen_id = entry.get("screen")
        breakpoint_name = entry.get("breakpoint")
        theme = entry.get("theme")
        known = True
        if not isinstance(screen_id, str) or screen_id not in facts["screen_ids"]:
            errors.append(
                f"{where}.screen: unknown screen {screen_id!r} "
                "(not declared in config.screens)"
            )
            known = False
        if (
            not isinstance(breakpoint_name, str)
            or breakpoint_name not in facts["breakpoint_names"]
        ):
            errors.append(
                f"{where}.breakpoint: unknown breakpoint {breakpoint_name!r} "
                "(not declared in config.breakpoints)"
            )
            known = False
        if not isinstance(theme, str) or theme not in facts["theme_names"]:
            errors.append(
                f"{where}.theme: unknown theme {theme!r} "
                "(not declared in config.themes)"
            )
            known = False

        diff_ratio = entry.get("diff_ratio")
        diff_ok = _is_ratio(diff_ratio)
        if not diff_ok:
            errors.append(f"{where}.diff_ratio: number in [0, 1] required")

        for field in ("baseline_sha", "current_sha"):
            value = entry.get(field)
            if not _nonempty(value):
                errors.append(f"{where}.{field}: non-empty string required")
            elif not HEX8_RE.match(value.strip()):
                warnings.append(
                    f"{where}.{field}: shorter than 8 hex chars "
                    "(recommended; value kept)"
                )

        artifact = entry.get("artifact")
        if artifact is not None and not isinstance(artifact, str):
            errors.append(f"{where}.artifact: string required when set")
        elif diff_ok and diff_ratio > 0 and not (artifact or "").strip():
            warnings.append(
                f"{where}: diff_ratio {_num(diff_ratio)} > 0 but artifact is empty; "
                "add the screenshot path"
            )

        if not known:
            continue

        key = (screen_id, breakpoint_name, theme)
        if key in covered:
            duplicates.append(_key(key))
            errors.append(f"{where}: duplicate combination {_key(key)}")
            continue
        covered.add(key)

        if diff_ok:
            critical = screen_id in facts["critical_ids"]
            if critical:
                limit = facts["critical_max_diff_ratio"]
                label = "critical "
            else:
                limit = facts["max_diff_ratio"]
                label = ""
            if diff_ratio > limit:
                failures.append(
                    f"{_key(key)}: diff_ratio {_num(diff_ratio)} exceeds "
                    f"{label}threshold {_num(limit)}"
                )

    missing = [
        _key((combo[0]["id"], combo[1]["name"], combo[2]))
        for combo in expected
        if (combo[0]["id"], combo[1]["name"], combo[2]) not in covered
    ]
    for combo_key in missing:
        errors.append(f"screens: missing combination {combo_key}")

    coverage.update(
        covered=len(covered),
        missing=missing,
        duplicates=duplicates,
    )
    return _report(facts["tool"], coverage, failures, warnings, errors)


# --- capture helpers -------------------------------------------------------


def _parse_stdout(stdout: str) -> tuple[dict | None, str | None]:
    text = stdout.strip()
    if not text:
        return None, "empty stdout (expected one JSON object)"
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None, "stdout is not one JSON object"
    if not isinstance(payload, dict):
        return None, "stdout JSON must be an object"
    return payload, None


def _capture_entry(
    payload: dict, screen: dict, breakpoint: dict, theme: str
) -> tuple[dict | None, list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    diff_ratio = payload.get("diff_ratio")
    if not _is_ratio(diff_ratio):
        errors.append("diff_ratio: number in [0, 1] required")

    baseline_sha = payload.get("baseline_sha")
    if not _nonempty(baseline_sha):
        errors.append("baseline_sha: non-empty string required")

    current_sha = payload.get("current_sha")
    if not _nonempty(current_sha):
        errors.append(
            "current_sha: non-empty string required "
            "(the tool must supply it; 'unknown' is not accepted)"
        )
    elif current_sha.strip().lower() == "unknown":
        errors.append(
            "current_sha: placeholder 'unknown' is not accepted; "
            "the tool must supply a real SHA"
        )

    artifact = payload.get("artifact")
    if artifact is not None and not isinstance(artifact, str):
        errors.append("artifact: string required when set")

    if errors:
        return None, errors, warnings

    where = _key((screen["id"], breakpoint["name"], theme))
    entry = {
        "screen": screen["id"],
        "breakpoint": breakpoint["name"],
        "theme": theme,
        "diff_ratio": diff_ratio,
        "baseline_sha": baseline_sha,
        "current_sha": current_sha,
    }
    if isinstance(artifact, str) and artifact.strip():
        entry["artifact"] = artifact
    elif diff_ratio > 0:
        warnings.append(
            f"{where}: diff_ratio {_num(diff_ratio)} > 0 but artifact is empty; "
            "add the screenshot path"
        )
    return entry, [], warnings


def _failure_results(tool, errors: list[str], screens: list[dict] | None = None) -> dict:
    return {
        "version": 1,
        "tool": tool,
        "generated_at": _iso(_utcnow()),
        "tool_available": False,
        "screens": list(screens or []),
        "errors": list(errors),
    }


def _emit_check(report: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    print("VISUAL: OK" if report["ok"] else "VISUAL: FAIL")
    if report.get("tool"):
        print(f"  tool: {report['tool']}")
    coverage = report["coverage"]
    print(f"  coverage: {coverage['covered']}/{coverage['expected']}")
    for failure in report["failures"]:
        print("  FAIL:", failure)
    for error in report["errors"]:
        print("  ERROR:", error)
    for warning in report["warnings"]:
        print("  WARN:", warning)


def _emit_capture(report: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _emit_check(report, False)


def _add_capture_context(report: dict, out: Path, captured: int, expected: int) -> dict:
    report["out"] = str(out)
    report["captured"] = captured
    report["expected"] = expected
    return report


# --- commands --------------------------------------------------------------


def cmd_init(args) -> int:
    path = Path(args.out)
    if path.exists() and not args.force:
        errors = [f"{path} already exists; use --force to overwrite"]
        report = {
            "ok": False,
            "path": str(path),
            "created": False,
            "errors": errors,
            "warnings": [],
        }
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print("VISUAL: FAIL")
            print("  ERROR:", errors[0])
        return 1

    try:
        _write_json(path, INIT_CONFIG)
    except OSError as exc:
        errors = [f"init: cannot write {path}: {exc}"]
        report = {
            "ok": False,
            "path": str(path),
            "created": False,
            "errors": errors,
            "warnings": [],
        }
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print("VISUAL: FAIL")
            print("  ERROR:", errors[0])
        return 1

    report = {
        "ok": True,
        "path": str(path),
        "created": True,
        "errors": [],
        "warnings": [],
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("VISUAL: OK")
        print(f"  config: {path}")
    return 0


def cmd_check(args) -> int:
    config, error = _read_json(args.config, "config")
    if error:
        report = _report(None, _empty_coverage(), [], [], [error])
        _emit_check(report, args.json)
        return 1

    config_errors, config_warnings = validate_config(config)
    if config_errors:
        report = _report(
            config.get("tool") if isinstance(config, dict) else None,
            _empty_coverage(),
            [],
            config_warnings,
            config_errors,
        )
        _emit_check(report, args.json)
        return 1

    results, error = _read_json(args.results, "results")
    if error:
        report = _report(_facts(config)["tool"], _empty_coverage(), [], config_warnings, [error])
        _emit_check(report, args.json)
        return 1

    report = assess_results(config, results)
    report["warnings"] = _dedupe(config_warnings + report["warnings"])
    _emit_check(report, args.json)
    return 0 if report["ok"] else 1


def cmd_capture(args) -> int:
    config, error = _read_json(args.config, "config")
    if error:
        report = _report(None, _empty_coverage(), [], [], [error])
        _emit_check(report, args.json)
        return 1

    config_errors, config_warnings = validate_config(config)
    if config_errors:
        errors = list(config_errors)
        try:
            _write_json(
                args.out,
                _failure_results(
                    config.get("tool") if isinstance(config, dict) else None,
                    errors,
                ),
            )
        except OSError as exc:
            errors.append(f"capture: cannot write {args.out}: {exc}")
        report = _report(
            config.get("tool") if isinstance(config, dict) else None,
            _empty_coverage(),
            [],
            config_warnings,
            errors,
        )
        _emit_capture(report, args.json)
        return 1

    facts = _facts(config)
    combinations = _combinations(facts)
    setup_errors: list[str] = []
    command = facts["command"]
    if not isinstance(command, list) or not command:
        setup_errors.append("command: non-empty list required for capture")

    cwd = None
    if args.cwd:
        cwd = Path(args.cwd).resolve()
        if not cwd.is_dir():
            setup_errors.append(f"--cwd: directory not found: {args.cwd}")

    for i, screen in enumerate(facts["screens"]):
        if not _nonempty(screen.get("url")):
            setup_errors.append(f"screens[{i}].url: non-empty URL/path required for capture")

    if setup_errors:
        results = _failure_results(facts["tool"], setup_errors)
        try:
            _write_json(args.out, results)
        except OSError as exc:
            setup_errors.append(f"capture: cannot write {args.out}: {exc}")
        report = assess_results(config, results)
        report["errors"] = setup_errors + report["errors"]
        report["ok"] = False
        report["warnings"] = _dedupe(config_warnings + report["warnings"])
        _emit_capture(
            _add_capture_context(report, Path(args.out), 0, len(combinations)),
            args.json,
        )
        return 1

    screens: list[dict] = []
    errors: list[str] = []
    warnings: list[str] = []

    for screen, breakpoint, theme in combinations:
        where = _key((screen["id"], breakpoint["name"], theme))
        env = os.environ.copy()
        env.update(
            {
                "KAR_VISUAL_SCREEN": str(screen["id"]),
                "KAR_VISUAL_BREAKPOINT": str(breakpoint["name"]),
                "KAR_VISUAL_THEME": str(theme),
                "KAR_VISUAL_URL": str(screen["url"]),
                "KAR_VISUAL_WIDTH": str(breakpoint["width"]),
            }
        )
        try:
            proc = subprocess.run(
                command,
                cwd=str(cwd) if cwd else None,
                env=env,
                text=True,
                capture_output=True,
                timeout=args.timeout,
            )
        except subprocess.TimeoutExpired:
            errors.append(f"{where}: command timed out after {args.timeout:g}s")
            continue
        except OSError as exc:
            errors.append(f"{where}: cannot run command: {exc}")
            continue

        if proc.returncode != 0:
            detail = _truncate(proc.stderr or proc.stdout)
            suffix = f": {detail}" if detail else ""
            errors.append(f"{where}: command exited with status {proc.returncode}{suffix}")
            continue

        payload, parse_error = _parse_stdout(proc.stdout)
        if parse_error:
            errors.append(f"{where}: {parse_error}")
            continue

        entry, entry_errors, entry_warnings = _capture_entry(
            payload, screen, breakpoint, theme
        )
        if entry_errors:
            errors.extend(f"{where}: {item}" for item in entry_errors)
            continue
        screens.append(entry)
        warnings.extend(entry_warnings)

    results = {
        "version": 1,
        "tool": facts["tool"],
        "generated_at": _iso(_utcnow()),
        "tool_available": not errors,
        "screens": screens,
    }
    if errors:
        results["errors"] = errors
    if warnings:
        results["warnings"] = warnings
    try:
        _write_json(args.out, results)
    except OSError as exc:
        errors.append(f"capture: cannot write {args.out}: {exc}")
        results["tool_available"] = False
        results["errors"] = errors

    report = assess_results(config, results)
    if errors:
        report["errors"] = _dedupe(errors + report["errors"])
        report["ok"] = False
    report["warnings"] = _dedupe(config_warnings + warnings + report["warnings"])
    _emit_capture(
        _add_capture_context(report, Path(args.out), len(screens), len(combinations)),
        args.json,
    )
    return 0 if report["ok"] and results["tool_available"] else 1


# --- CLI -------------------------------------------------------------------


def _positive_float(value: str) -> float:
    try:
        number = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid number: {value!r}") from exc
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("timeout must be a positive number of seconds")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="KAR v4.4 visual regression adapter (stdlib only)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Write a project visual.json template")
    p_init.add_argument("--out", required=True)
    p_init.add_argument("--force", action="store_true")
    p_init.add_argument("--json", action="store_true")
    p_init.set_defaults(func=cmd_init)

    p_check = sub.add_parser("check", help="Validate config/results, coverage and thresholds")
    p_check.add_argument("--config", required=True)
    p_check.add_argument("--results", required=True)
    p_check.add_argument("--json", action="store_true")
    p_check.set_defaults(func=cmd_check)

    p_capture = sub.add_parser("capture", help="Run the declared tool for every combination")
    p_capture.add_argument("--config", required=True)
    p_capture.add_argument("--out", required=True)
    p_capture.add_argument("--cwd")
    p_capture.add_argument("--timeout", type=_positive_float, default=120.0)
    p_capture.add_argument("--json", action="store_true")
    p_capture.set_defaults(func=cmd_capture)

    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
