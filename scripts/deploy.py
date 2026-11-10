#!/usr/bin/env python3
"""One-command workspace rollout: dry-run -> apply --update -> verify.

Default is dry-run: only ``bootstrap.py --dry-run`` is called and nothing is
written. ``--apply`` requires ``--approved-by <human>``; it runs bootstrap with
an automatic backup, then verify, and stops at the first failure.
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parent.parent
STEP_NAMES = ("version/spec check", "bootstrap dry-run", "bootstrap apply", "verify")
INTERPRETER = sys.executable or "python3"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def run_command(
    cmd: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    timeout: int = 600,
) -> tuple[int, str, str]:
    """Run a command without a shell; return (returncode, stdout, stderr)."""
    argv = [str(part) for part in cmd]
    try:
        proc = subprocess.run(
            argv,
            cwd=str(cwd),
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except FileNotFoundError as exc:
        return 127, "", f"command not found: {argv[0]} ({exc})"
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", "replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", "replace")
        return 124, stdout, f"timed out after {timeout}s\n{stderr}"
    except OSError as exc:
        return 126, "", f"cannot execute {argv[0]}: {exc}"


def format_command(cmd: list[str]) -> str:
    return shlex.join([str(part) for part in cmd])


def resolve_script(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def script_command(script: Path) -> list[str]:
    """Run a .py script with the current interpreter, anything else directly."""
    if str(script).endswith(".py"):
        return [INTERPRETER, str(script)]
    return [str(script)]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def version_check(root: Path) -> tuple[str, list[str]]:
    """Step 1: VERSION and bootstrap.json must agree; no Multica access."""
    errors: list[str] = []
    version = ""
    try:
        version = read_text(root / "VERSION")
    except OSError as exc:
        errors.append(f"cannot read VERSION: {exc}")
    if not version:
        errors.append("VERSION is missing or empty")
    try:
        bootstrap = json.loads((root / "bootstrap.json").read_text(encoding="utf-8"))
    except OSError as exc:
        errors.append(f"cannot read bootstrap.json: {exc}")
    except json.JSONDecodeError as exc:
        errors.append(f"bootstrap.json is not valid JSON: {exc}")
    else:
        if not isinstance(bootstrap, dict):
            errors.append("bootstrap.json must be a JSON object")
            bootstrap = {}
        bootstrap_version = bootstrap.get("version")
        if version and bootstrap_version != version:
            errors.append(
                f"bootstrap.json version {bootstrap_version} != VERSION {version}"
            )
    return version, errors


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------


def bootstrap_args(args: argparse.Namespace, root: Path, *, apply: bool) -> list[str]:
    script = resolve_script(root, args.bootstrap_script)
    cmd = script_command(script)
    cmd.append("--apply" if apply else "--dry-run")
    if args.multica:
        cmd += ["--multica", args.multica]
    if args.workspace_id:
        cmd += ["--workspace-id", args.workspace_id]
    if args.core_runtime:
        cmd += ["--core-runtime", args.core_runtime]
    if args.qa_runtime:
        cmd += ["--qa-runtime", args.qa_runtime]
    if args.profile:
        cmd += ["--profile", args.profile]
    if args.backup_dir:
        cmd += ["--backup-dir", args.backup_dir]
    if apply and args.update:
        cmd.append("--update")
    return cmd


def verify_args(args: argparse.Namespace, root: Path) -> list[str]:
    script = resolve_script(root, args.verify_script)
    cmd = script_command(script)
    if args.multica:
        cmd += ["--multica", args.multica]
    if args.workspace_id:
        cmd += ["--workspace-id", args.workspace_id]
    if args.profile:
        cmd += ["--profile", args.profile]
    return cmd


def print_table(records: list[dict]) -> None:
    print("")
    print(f"{'STEP':<26}{'EXIT':<8}RESULT")
    print("-" * 48)
    for index, record in enumerate(records, start=1):
        label = f"{index} {record['name']}"
        code = "-" if record.get("returncode") is None else str(record["returncode"])
        print(f"{label:<26}{code:<8}{record['status']}")


def emit(args: argparse.Namespace, payload: dict) -> None:
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))


def mark_skipped(records: list[dict], start: int, note: str) -> None:
    for record in records[start:]:
        if record["status"] == "pending":
            record["status"] = "skipped"
            record["note"] = note


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="KAR Squad OS workspace rollout (dry-run by default)"
    )
    parser.add_argument(
        "--root",
        default=str(SCRIPT_ROOT),
        help="Repository root (default: parent of scripts/)",
    )
    parser.add_argument("--apply", action="store_true", help="Actually write the workspace")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Explicit dry-run (the default); cannot be combined with --apply",
    )
    parser.add_argument("--approved-by", default="", help="Human approval reference (required with --apply)")
    parser.add_argument(
        "--update",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Update existing objects when applying (default: true)",
    )
    parser.add_argument(
        "--multica",
        default=os.environ.get("MULTICA_CLI_PATH") or os.environ.get("MULTICA") or "multica",
    )
    parser.add_argument("--workspace-id", default=os.environ.get("MULTICA_WORKSPACE_ID", ""))
    parser.add_argument("--core-runtime", default=os.environ.get("KAR_CORE_RUNTIME_ID", ""))
    parser.add_argument("--qa-runtime", default=os.environ.get("KAR_QA_RUNTIME_ID", ""))
    parser.add_argument("--profile", default=os.environ.get("MULTICA_PROFILE", ""))
    parser.add_argument("--backup-dir", default="backups")
    parser.add_argument("--bootstrap-script", default="scripts/bootstrap.py")
    parser.add_argument("--verify-script", default="scripts/verify.py")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.apply and args.dry_run:
        parser.error("--dry-run and --apply are mutually exclusive")
    if args.dry_run:
        args.apply = False

    root = Path(args.root).resolve()
    if not root.is_dir():
        message = f"root does not exist: {root}"
        if args.json:
            print(json.dumps({"ok": False, "errors": [message], "steps": []}, ensure_ascii=False, indent=2))
        else:
            print(f"DEPLOY: FAIL\n  {message}", file=sys.stderr)
        return 1

    records = [
        {"name": name, "command": None, "returncode": None, "status": "pending"}
        for name in STEP_NAMES
    ]
    errors: list[str] = []
    version = ""
    deployed = False

    def finish(ok: bool, failed_step: str = "") -> int:
        if not args.json:
            print_table(records)
            print(f"version: {version or '<unknown>'}")
            print(f"deployed: {'yes' if deployed else 'no'} (update={'yes' if args.update else 'no'})")
            if not ok:
                print(f"DEPLOY: FAIL at step {failed_step}", file=sys.stderr)
        payload = {
            "ok": ok,
            "dry_run": not args.apply,
            "version": version,
            "approved_by": args.approved_by,
            "deployed": deployed,
            "steps": records,
            "errors": errors,
        }
        emit(args, payload)
        return 0 if ok else 1

    if args.apply and not args.approved_by.strip():
        message = "--apply requires --approved-by <human>"
        errors.append(message)
        if not args.json:
            print(f"DEPLOY: FAIL\n  {message}", file=sys.stderr)
        payload = {
            "ok": False,
            "dry_run": False,
            "version": "",
            "approved_by": args.approved_by,
            "deployed": False,
            "steps": records,
            "errors": errors,
        }
        emit(args, payload)
        return 1

    if args.timeout <= 0:
        errors.append("--timeout must be a positive integer")
        if not args.json:
            print("DEPLOY: FAIL\n  --timeout must be a positive integer", file=sys.stderr)
        emit(args, {
            "ok": False,
            "dry_run": not args.apply,
            "version": version,
            "approved_by": args.approved_by,
            "deployed": False,
            "steps": records,
            "errors": errors,
        })
        return 1

    # Step 1: version/spec check.
    if not args.json:
        print(f"[1/4] {STEP_NAMES[0]}")
    version, step_errors = version_check(root)
    records[0]["command"] = ["version_check", str(root / "VERSION"), str(root / "bootstrap.json")]
    if step_errors:
        records[0]["status"] = "failed"
        records[0]["returncode"] = 1
        errors.extend(step_errors)
        if not args.json:
            for item in step_errors:
                print(f"  ERROR: {item}", file=sys.stderr)
        mark_skipped(records, 1, "not run; version/spec check failed")
        return finish(False, STEP_NAMES[0])
    records[0]["status"] = "ok"
    records[0]["returncode"] = 0
    if not args.json:
        print(f"  version: {version}; bootstrap.json matches")

    # Step 2: bootstrap dry-run (always; the only call made in dry-run mode).
    dry_cmd = bootstrap_args(args, root, apply=False)
    records[1]["command"] = dry_cmd
    if not args.json:
        print(f"[2/4] {STEP_NAMES[1]}: {format_command(dry_cmd)}")
    rc, out, err = run_command(dry_cmd, cwd=root, timeout=args.timeout)
    records[1]["returncode"] = rc
    records[1]["status"] = "ok" if rc == 0 else "failed"
    if not args.json:
        if out.strip():
            print(out.rstrip())
        if err.strip():
            print(err.rstrip(), file=sys.stderr)
    if rc != 0:
        errors.append(f"{STEP_NAMES[1]} exited {rc}: {(err or out).strip()}")
        mark_skipped(records, 2, "not run; bootstrap dry-run failed")
        return finish(False, STEP_NAMES[1])

    if not args.apply:
        mark_skipped(records, 2, "dry-run only; nothing written")
        if not args.json:
            print("dry-run only; re-run with --apply --approved-by <human> to write")
        return finish(True)

    # Step 3: bootstrap --apply (+ --update unless --no-update).
    apply_cmd = bootstrap_args(args, root, apply=True)
    records[2]["command"] = apply_cmd
    if not args.json:
        print(f"[3/4] {STEP_NAMES[2]}: {format_command(apply_cmd)}")
    rc, out, err = run_command(apply_cmd, cwd=root, timeout=args.timeout)
    records[2]["returncode"] = rc
    records[2]["status"] = "ok" if rc == 0 else "failed"
    if not args.json:
        if out.strip():
            print(out.rstrip())
        if err.strip():
            print(err.rstrip(), file=sys.stderr)
    if rc != 0:
        errors.append(f"{STEP_NAMES[2]} exited {rc}: {(err or out).strip()}")
        mark_skipped(records, 3, "not run; bootstrap apply failed")
        return finish(False, STEP_NAMES[2])

    # Step 4: verify.
    check_cmd = verify_args(args, root)
    records[3]["command"] = check_cmd
    if not args.json:
        print(f"[4/4] {STEP_NAMES[3]}: {format_command(check_cmd)}")
    rc, out, err = run_command(check_cmd, cwd=root, timeout=args.timeout)
    records[3]["returncode"] = rc
    records[3]["status"] = "ok" if rc == 0 else "failed"
    if not args.json:
        if out.strip():
            print(out.rstrip())
        if err.strip():
            print(err.rstrip(), file=sys.stderr)
    if rc != 0:
        errors.append(f"{STEP_NAMES[3]} exited {rc}: {(err or out).strip()}")
        return finish(False, STEP_NAMES[3])

    deployed = True
    return finish(True)


if __name__ == "__main__":
    sys.exit(main())
