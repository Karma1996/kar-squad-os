#!/usr/bin/env python3
"""Release automation: check, plan, tag, GitHub Release, Multica attachment.

Every irreversible action is dry-run by default. ``tag --apply``,
``github-release --apply``, ``attach --apply`` and ``publish --apply`` require a
human approval reference (``--approved-by``) and an explicit ``--apply``.
External commands (``git`` / ``gh`` / ``multica``) can be injected, so CI can
verify the exact argv with fake executables and never touch the network.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parent.parent
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
DEFAULT_TITLE = "KAR Squad OS v{version}"
INTERPRETER = "python3"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def run_command(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    timeout: int | None = None,
) -> tuple[int, str, str]:
    """Run a command without a shell; return (returncode, stdout, stderr)."""
    argv = [str(part) for part in cmd]
    try:
        proc = subprocess.run(
            argv,
            cwd=str(cwd) if cwd else None,
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


def read_version(root: Path) -> str:
    try:
        return (root / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_path(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def artifact_rel(version: str) -> str:
    return f"release/KAR-Squad-Bootstrap-v{version}.zip"


def tag_for(version: str) -> str:
    return f"v{version}" if version else ""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fail(message: str) -> int:
    print(message, file=sys.stderr)
    return 1


def print_errors(prefix: str, errors: list[str]) -> None:
    for item in errors:
        print(f"  {prefix}: {item}")


# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------


def changelog_section(root: Path, version: str) -> str:
    """Return the CHANGELOG body between ``## <version>`` and the next ``## ``."""
    try:
        text = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    except OSError:
        return ""
    heading = re.compile(rf"^##\s+{re.escape(version)}(?:\s|$)")
    next_heading = re.compile(r"^##\s+")
    body: list[str] = []
    inside = False
    for line in text.splitlines():
        if not inside:
            if heading.match(line):
                inside = True
            continue
        if next_heading.match(line):
            break
        body.append(line.rstrip())
    while body and not body[-1].strip():
        body.pop()
    while body and not body[0].strip():
        body.pop(0)
    return "\n".join(body)


def release_notes_body(root: Path, version: str) -> str:
    section = changelog_section(root, version)
    if not section:
        section = f"- Release v{version}."
    return f"# KAR Squad OS v{version}\n\n{section}\n"


def check_release(root: Path, *, allow_dirty: bool = False, git: str = "git") -> dict:
    """Validate release readiness without changing anything."""
    errors: list[str] = []
    warnings: list[str] = []
    version = read_version(root)
    if not version:
        errors.append(f"missing or empty VERSION at {root / 'VERSION'}")
    elif not SEMVER.match(version):
        errors.append(f"VERSION {version!r} is not MAJOR.MINOR.PATCH")

    bootstrap: dict = {}
    bootstrap_path = root / "bootstrap.json"
    try:
        bootstrap = read_json(bootstrap_path)
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
            errors.append(f"bootstrap.json version {bootstrap_version} != VERSION {version}")
        config_rel = bootstrap.get("config")
        if not config_rel:
            errors.append("bootstrap.json has no config path")
        elif not (root / str(config_rel)).is_file():
            errors.append(f"config handbook does not exist: {config_rel}")

    profile_path = root / "skills/kar-squad-profile/squad.json"
    try:
        profile = read_json(profile_path)
    except OSError as exc:
        errors.append(f"cannot read {profile_path.relative_to(root)}: {exc}")
    except json.JSONDecodeError as exc:
        errors.append(f"{profile_path.relative_to(root)} is not valid JSON: {exc}")
    else:
        if not isinstance(profile, dict):
            errors.append(f"{profile_path.relative_to(root)} must be a JSON object")
            profile = {}
        if version and profile.get("version") != version:
            errors.append(
                f"kar-squad-profile version {profile.get('version')} != VERSION {version}"
            )

    if version:
        try:
            changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
        except OSError as exc:
            errors.append(f"cannot read CHANGELOG.md: {exc}")
        else:
            if not re.search(rf"^##\s+{re.escape(version)}(?:\s|$)", changelog, re.MULTILINE):
                errors.append(f"CHANGELOG.md has no '## {version}' heading")

    rc, out, err = run_command([git, "-C", str(root), "status", "--porcelain"])
    if rc != 0:
        detail = (err or out).strip()
        lowered = detail.lower()
        if (
            "not a git repository" in lowered
            or "not a git repo" in lowered
            or not (root / ".git").exists()
        ):
            warnings.append("root is not a git repository; working tree check was skipped")
        else:
            errors.append(f"git status failed (exit {rc}){': ' + detail if detail else ''}")
    elif out.strip():
        if allow_dirty:
            warnings.append("git working tree is dirty (allowed by --allow-dirty)")
        else:
            errors.append("git working tree is dirty")

    tag = tag_for(version)
    if tag:
        rc, out, err = run_command([git, "-C", str(root), "tag", "--list", tag])
        if rc != 0:
            detail = (err or out).strip()
            warnings.append(f"cannot check local tag {tag} (exit {rc}){': ' + detail if detail else ''}")
        elif tag in out.split():
            warnings.append(
                f"local tag {tag} already exists; publish will fail (tags are immutable)"
            )

    return {
        "ok": not errors,
        "version": version,
        "tag": tag,
        "artifact": artifact_rel(version) if version else "",
        "errors": errors,
        "warnings": warnings,
    }


def print_check(report: dict) -> None:
    print(f"RELEASE CHECK: {'OK' if report['ok'] else 'FAIL'}")
    print(f"  version: {report['version'] or '<missing>'}")
    print(f"  tag: {report['tag'] or '<missing>'}")
    print(f"  artifact: {report['artifact'] or '<missing>'}")
    print_errors("ERROR", report["errors"])
    print_errors("WARN", report["warnings"])


# ---------------------------------------------------------------------------
# plan / tag
# ---------------------------------------------------------------------------


def plan_steps(version: str, tag: str, artifact: str) -> list[dict]:
    note_path = f"release/RELEASE-NOTES-v{version}.md"
    body_path = f"release/KAR-Squad-{tag}-attachment.md"
    return [
        {
            "name": "build",
            "command": format_command([INTERPRETER, "scripts/build_release.py"]),
        },
        {
            "name": "tag",
            "command": format_command(
                ["git", "tag", "-a", tag, "-m", f"KAR Squad OS {tag}"]
            ),
        },
        {
            "name": "push",
            "command": format_command(["git", "push", "origin", tag]),
        },
        {
            "name": "github-release",
            "command": format_command(
                [
                    "gh",
                    "release",
                    "create",
                    tag,
                    artifact,
                    "--title",
                    DEFAULT_TITLE.format(version=version),
                    "--notes-file",
                    note_path,
                ]
            ),
        },
        {
            "name": "attach",
            "command": format_command(
                [
                    "multica",
                    "issue",
                    "comment",
                    "add",
                    "KAR-ISSUE",
                    "--content-file",
                    body_path,
                    "--attachment",
                    artifact,
                ]
            ),
        },
    ]


def command_plan(args: argparse.Namespace, root: Path, version: str) -> int:
    expected = tag_for(version)
    if not version or not SEMVER.match(version):
        return fail(f"RELEASE PLAN: FAIL\n  invalid VERSION {version!r}")
    if args.tag != expected:
        return fail(
            f"RELEASE PLAN: FAIL\n  tag {args.tag} != v{{VERSION}} ({expected})"
        )
    artifact = artifact_rel(version)
    steps = plan_steps(version, expected, artifact)
    if args.json:
        print(json.dumps(
            {
                "ok": True,
                "version": version,
                "tag": expected,
                "artifact": artifact,
                "steps": steps,
            },
            ensure_ascii=False,
            indent=2,
        ))
        return 0
    print(f"RELEASE PLAN: {expected}")
    for index, step in enumerate(steps, start=1):
        print(f"  {index}. {step['name']:<15} {step['command']}")
    print(f"  artifact: {artifact}")
    print("  no side effects; pass --apply to tag/github-release/attach (with --approved-by).")
    return 0


def tag_action(
    root: Path,
    *,
    version: str,
    tag: str,
    approved_by: str,
    apply: bool,
    push: bool,
    remote: str,
    git: str,
) -> int:
    """Create (and optionally push) an annotated tag. Dry-run by default."""
    expected = tag_for(version)
    if tag != expected:
        return fail(f"RELEASE TAG: FAIL\n  tag {tag} != v{{VERSION}} ({expected})")
    if not approved_by.strip():
        return fail("RELEASE TAG: FAIL\n  --approved-by <human> is required")
    tag_cmd = [git, "tag", "-a", tag, "-m", f"KAR Squad OS {tag}"]
    push_cmd = [git, "push", remote, tag]
    if not apply:
        print(f"DRY-RUN: {format_command(tag_cmd)}")
        print(f"tag: {tag} (dry-run; not created)")
        if push:
            print(f"DRY-RUN: {format_command(push_cmd)}")
            print(f"push: {remote} {tag} (dry-run; not pushed)")
        else:
            print("push: skipped (pass --push to publish the tag)")
        return 0

    rc, out, err = run_command([git, "tag", "--list", tag], cwd=root)
    if rc != 0:
        return fail(f"RELEASE TAG: FAIL\n  cannot list tags: {err or out}")
    if tag in out.split():
        return fail(
            f"RELEASE TAG: FAIL\n  tag {tag} already exists; tags are immutable"
        )

    print(f"APPROVED BY: {approved_by}")
    rc, out, err = run_command(tag_cmd, cwd=root)
    if rc != 0:
        print(err or out, file=sys.stderr)
        return fail(f"RELEASE TAG: FAIL\n  git tag exited {rc}")
    print(f"TAG: {tag} created")

    if not push:
        print("PUSH: skipped (pass --push to publish the tag)")
        return 0
    rc, out, err = run_command(push_cmd, cwd=root)
    if rc != 0:
        print(err or out, file=sys.stderr)
        return fail(f"RELEASE TAG: FAIL\n  git push {remote} {tag} exited {rc}")
    print(f"PUSH: {remote} {tag} pushed")
    return 0


# ---------------------------------------------------------------------------
# github release / multica attachment
# ---------------------------------------------------------------------------


def github_release_action(
    root: Path,
    *,
    version: str,
    tag: str,
    artifact_arg: str,
    gh: str,
    apply: bool,
    notes_file: str,
    title: str,
) -> int:
    expected = tag_for(version)
    if tag != expected:
        return fail(f"GITHUB RELEASE: FAIL\n  tag {tag} != v{{VERSION}} ({expected})")
    artifact = resolve_path(root, artifact_arg)
    if not artifact.is_file():
        return fail(f"GITHUB RELEASE: FAIL\n  artifact does not exist: {artifact}")
    effective_title = title.strip() or DEFAULT_TITLE.format(version=version)

    if notes_file:
        notes_path = resolve_path(root, notes_file)
        if not notes_path.is_file():
            return fail(f"GITHUB RELEASE: FAIL\n  notes file does not exist: {notes_path}")
        generated = False
    else:
        notes_path = root / "release" / f"RELEASE-NOTES-v{version}.md"
        generated = True

    cmd = [
        gh,
        "release",
        "create",
        tag,
        str(artifact),
        "--title",
        effective_title,
        "--notes-file",
        str(notes_path),
    ]
    if not apply:
        print(f"DRY-RUN: {format_command(cmd)}")
        print(f"GITHUB RELEASE: {tag} (dry-run; no release created)")
        return 0

    if generated:
        notes_path.parent.mkdir(parents=True, exist_ok=True)
        notes_path.write_text(release_notes_body(root, version), encoding="utf-8")
        print(f"notes written: {notes_path}")

    rc, out, err = run_command(cmd, cwd=root)
    if rc != 0:
        if out.strip():
            print(out.strip(), file=sys.stderr)
        print(err.strip(), file=sys.stderr)
        return fail(f"GITHUB RELEASE: FAIL\n  gh release create exited {rc}")
    print(f"GITHUB RELEASE: {tag} created")
    if out.strip():
        print(out.strip())
    return 0


def attachment_body(
    *, tag: str, artifact: Path, digest: str, approved_by: str
) -> str:
    approver = approved_by.strip() or "human"
    return (
        f"# KAR Squad OS {tag}\n\n"
        f"- 发布 tag: {tag}\n"
        f"- 发布包: {artifact.name}\n"
        f"- sha256: {digest}\n"
        f"- 发布由 {approver} 批准\n"
    )


def attach_action(
    root: Path,
    *,
    version: str,
    issue: str,
    artifact_arg: str,
    tag: str,
    multica: str,
    apply: bool,
    body_file: str,
    approved_by: str,
) -> int:
    expected = tag_for(version)
    if tag != expected:
        return fail(f"ATTACH: FAIL\n  tag {tag} != v{{VERSION}} ({expected})")
    if not issue.strip():
        return fail("ATTACH: FAIL\n  --issue is required")
    artifact = resolve_path(root, artifact_arg)
    if not artifact.is_file():
        return fail(f"ATTACH: FAIL\n  artifact does not exist: {artifact}")

    if body_file:
        body_path = resolve_path(root, body_file)
    else:
        safe_issue = re.sub(r"[^A-Za-z0-9_.-]+", "-", issue)
        body_path = root / "release" / f"KAR-Squad-{safe_issue}-{tag}-attachment.md"
    cmd = [
        multica,
        "issue",
        "comment",
        "add",
        issue,
        "--content-file",
        str(body_path),
        "--attachment",
        str(artifact),
    ]
    if not apply:
        print(f"DRY-RUN: {format_command(cmd)}")
        print(f"ATTACH: {issue} (dry-run; no comment posted)")
        return 0

    digest = sha256_file(artifact)
    body_path.parent.mkdir(parents=True, exist_ok=True)
    body_path.write_text(
        attachment_body(tag=tag, artifact=artifact, digest=digest, approved_by=approved_by),
        encoding="utf-8",
    )
    print(f"comment body written: {body_path}")

    rc, out, err = run_command(cmd, cwd=root)
    if rc != 0:
        if out.strip():
            print(out.strip(), file=sys.stderr)
        print(err.strip(), file=sys.stderr)
        return fail(f"ATTACH: FAIL\n  multica issue comment add exited {rc}")
    print(f"ATTACH: {issue} comment posted")
    if out.strip():
        print(out.strip())
    return 0


# ---------------------------------------------------------------------------
# publish
# ---------------------------------------------------------------------------


def command_publish(args: argparse.Namespace, root: Path, version: str) -> int:
    expected = tag_for(version)
    if not approved_by_ok(args.approved_by):
        return fail("PUBLISH: FAIL\n  --approved-by <human> is required")
    if not version or not SEMVER.match(version):
        return fail(f"PUBLISH: FAIL\n  invalid VERSION {version!r}")
    if args.tag != expected:
        return fail(f"PUBLISH: FAIL\n  tag {args.tag} != v{{VERSION}} ({expected})")
    if not args.issue.strip():
        return fail("PUBLISH: FAIL\n  --issue is required")

    artifact_rel_path = artifact_rel(version)
    title = DEFAULT_TITLE.format(version=version)
    notes_path = root / "release" / f"RELEASE-NOTES-v{version}.md"
    safe_issue = re.sub(r"[^A-Za-z0-9_.-]+", "-", args.issue)
    body_path = root / "release" / f"KAR-Squad-{safe_issue}-{expected}-attachment.md"

    print(f"[1/5] check  (tag {expected}, artifact {artifact_rel_path})")
    report = check_release(root, allow_dirty=not args.apply)
    print_check(report)
    if not report["ok"]:
        return fail("PUBLISH: FAIL at step check")

    if not args.apply:
        build_cmd = [INTERPRETER, "scripts/build_release.py"]
        tag_cmd = [args.git, "tag", "-a", expected, "-m", f"KAR Squad OS {expected}"]
        push_cmd = [args.git, "push", args.remote, expected]
        gh_cmd = [
            args.gh,
            "release",
            "create",
            expected,
            str(root / artifact_rel_path),
            "--title",
            title,
            "--notes-file",
            str(notes_path),
        ]
        attach_cmd = [
            args.multica,
            "issue",
            "comment",
            "add",
            args.issue,
            "--content-file",
            str(body_path),
            "--attachment",
            str(root / artifact_rel_path),
        ]
        print(f"[2/5] build (dry-run)")
        print(f"DRY-RUN: {format_command(build_cmd)}")
        print(f"artifact: {artifact_rel_path} (will be created by build)")
        print(f"[3/5] tag (dry-run)")
        print(f"DRY-RUN: {format_command(tag_cmd)}")
        if args.push:
            print(f"DRY-RUN: {format_command(push_cmd)}")
        else:
            print("push: skipped (pass --push to publish the tag)")
        print(f"[4/5] github-release (dry-run)")
        print(f"DRY-RUN: {format_command(gh_cmd)}")
        print(f"[5/5] attach (dry-run)" if args.attach else "[5/5] attach (skipped; --no-attach)")
        if args.attach:
            print(f"DRY-RUN: {format_command(attach_cmd)}")
        print("PUBLISH: dry-run only; no build, tag, release, or comment was created.")
        return 0

    print("[2/5] build")
    build_cmd = [INTERPRETER, "scripts/build_release.py"]
    print(f"RUN: {format_command(build_cmd)}")
    rc, out, err = run_command(build_cmd, cwd=root)
    if out.strip():
        print(out.strip())
    if rc != 0:
        if err.strip():
            print(err.strip(), file=sys.stderr)
        return fail(f"PUBLISH: FAIL at step build (exit {rc})")
    artifact = root / artifact_rel_path
    if not artifact.is_file():
        return fail(f"PUBLISH: FAIL at step build\n  artifact was not created: {artifact}")
    print(f"BUILD: {artifact_rel_path}")

    print("[3/5] tag")
    rc = tag_action(
        root,
        version=version,
        tag=expected,
        approved_by=args.approved_by,
        apply=True,
        push=args.push,
        remote=args.remote,
        git=args.git,
    )
    if rc != 0:
        return fail("PUBLISH: FAIL at step tag")

    print("[4/5] github-release")
    rc = github_release_action(
        root,
        version=version,
        tag=expected,
        artifact_arg=str(artifact),
        gh=args.gh,
        apply=True,
        notes_file="",
        title=title,
    )
    if rc != 0:
        return fail("PUBLISH: FAIL at step github-release")

    if not args.attach:
        print("[5/5] attach (skipped; --no-attach)")
    else:
        print("[5/5] attach")
        rc = attach_action(
            root,
            version=version,
            issue=args.issue,
            artifact_arg=str(artifact),
            tag=expected,
            multica=args.multica,
            apply=True,
            body_file="",
            approved_by=args.approved_by,
        )
        if rc != 0:
            return fail("PUBLISH: FAIL at step attach")

    print(f"PUBLISH: OK  {expected}  approved-by={args.approved_by}")
    return 0


def approved_by_ok(value: str | None) -> bool:
    return bool(value and value.strip())


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="KAR Squad OS release automation (dry-run by default)"
    )
    parser.add_argument(
        "--root",
        default=str(SCRIPT_ROOT),
        help="Repository root (default: parent of scripts/)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="Validate release readiness")
    check.add_argument("--json", action="store_true")
    check.add_argument("--allow-dirty", action="store_true", help="Dirty tree is only a warning")

    plan = sub.add_parser("plan", help="Print the ordered release pipeline")
    plan.add_argument("--tag", required=True)
    plan.add_argument("--json", action="store_true")

    tag = sub.add_parser("tag", help="Create (and optionally push) an annotated tag")
    tag.add_argument("--tag", required=True)
    tag.add_argument("--approved-by", default="", help="Human approval reference")
    tag.add_argument("--apply", action="store_true", help="Actually create the tag")
    tag.add_argument("--push", action=argparse.BooleanOptionalAction, default=False)
    tag.add_argument("--remote", default="origin")
    tag.add_argument("--git", default="git")

    gh = sub.add_parser("github-release", help="Create a GitHub Release")
    gh.add_argument("--tag", required=True)
    gh.add_argument("--artifact", required=True)
    gh.add_argument("--gh", default="gh")
    gh.add_argument("--apply", action="store_true")
    gh.add_argument("--notes-file", default="")
    gh.add_argument("--title", default="")

    attach = sub.add_parser("attach", help="Attach the release zip to a Multica issue")
    attach.add_argument("--issue", required=True)
    attach.add_argument("--artifact", required=True)
    attach.add_argument("--tag", required=True)
    attach.add_argument("--multica", default="multica")
    attach.add_argument("--apply", action="store_true")
    attach.add_argument("--body-file", default="")
    attach.add_argument("--approved-by", default="", help="Optional human approval reference")

    publish = sub.add_parser("publish", help="Run check -> build -> tag -> release -> attach")
    publish.add_argument("--tag", required=True)
    publish.add_argument("--issue", required=True)
    publish.add_argument("--approved-by", required=True, help="Human approval reference")
    publish.add_argument("--apply", action="store_true")
    publish.add_argument("--push", action=argparse.BooleanOptionalAction, default=False)
    publish.add_argument("--attach", action=argparse.BooleanOptionalAction, default=True)
    publish.add_argument("--remote", default="origin")
    publish.add_argument("--git", default="git")
    publish.add_argument("--gh", default="gh")
    publish.add_argument("--multica", default="multica")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve()
    if not root.is_dir():
        return fail(f"RELEASE: FAIL\n  root does not exist: {root}")
    version = read_version(root)

    if args.command == "check":
        report = check_release(root, allow_dirty=args.allow_dirty)
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print_check(report)
        return 0 if report["ok"] else 1

    if args.command == "plan":
        return command_plan(args, root, version)

    if not version or not SEMVER.match(version):
        return fail(f"RELEASE: FAIL\n  invalid or missing VERSION {version!r}")

    if args.command == "tag":
        return tag_action(
            root,
            version=version,
            tag=args.tag,
            approved_by=args.approved_by,
            apply=args.apply,
            push=args.push,
            remote=args.remote,
            git=args.git,
        )
    if args.command == "github-release":
        return github_release_action(
            root,
            version=version,
            tag=args.tag,
            artifact_arg=args.artifact,
            gh=args.gh,
            apply=args.apply,
            notes_file=args.notes_file,
            title=args.title,
        )
    if args.command == "attach":
        return attach_action(
            root,
            version=version,
            issue=args.issue,
            artifact_arg=args.artifact,
            tag=args.tag,
            multica=args.multica,
            apply=args.apply,
            body_file=args.body_file,
            approved_by=args.approved_by,
        )
    if args.command == "publish":
        return command_publish(args, root, version)
    return fail(f"RELEASE: FAIL\n  unknown command {args.command}")


if __name__ == "__main__":
    sys.exit(main())
