#!/usr/bin/env python3
"""Tests for scripts/release.py using fake gh/multica and local-only git."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RELEASE = ROOT / "scripts/release.py"

FAKE = '''#!/usr/bin/env python3
import json
import os
import sys

args = sys.argv[1:]
log = os.environ.get("FAKE_LOG")
if log:
    with open(log, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(args, ensure_ascii=False) + "\\n")
matched = os.environ.get("FAKE_FAIL_MATCH", "")
if matched and matched in " ".join(args):
    print("fake failure", file=sys.stderr)
    sys.exit(1)
code = int(os.environ.get("FAKE_EXIT", "0"))
if code:
    print("fake failure", file=sys.stderr)
    sys.exit(code)
out = os.environ.get("FAKE_STDOUT")
if out:
    print(out)
sys.exit(0)
'''


def write_fake(directory: Path, name: str) -> Path:
    path = directory / name
    path.write_text(FAKE, encoding="utf-8")
    os.chmod(path, 0o755)
    return path


def git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        text=True,
        capture_output=True,
        check=check,
    )


def make_root(base: Path, version: str = "4.4.0", init_git: bool = True) -> Path:
    root = base / "repo"
    root.mkdir(parents=True)
    (root / "VERSION").write_text(version + "\n", encoding="utf-8")
    (root / "bootstrap.json").write_text(
        json.dumps(
            {
                "name": "KAR Delivery Squad",
                "version": version,
                "config": f"config/KAR-Squad-Config-v{version}.md",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "config").mkdir()
    (root / "config" / f"KAR-Squad-Config-v{version}.md").write_text(
        "# config\n", encoding="utf-8"
    )
    profile_dir = root / "skills" / "kar-squad-profile"
    profile_dir.mkdir(parents=True)
    (profile_dir / "squad.json").write_text(
        json.dumps({"version": version}) + "\n", encoding="utf-8"
    )
    (root / "CHANGELOG.md").write_text(
        "# Changelog\n\n"
        f"## {version}\n\n"
        "- release item one\n"
        "- release item two\n\n"
        "## 0.0.1\n\n"
        "- old\n",
        encoding="utf-8",
    )
    (root / "scripts").mkdir()
    if init_git:
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        for key, value in (
            ("user.name", "Release Test"),
            ("user.email", "release@example.invalid"),
            ("commit.gpgSign", "false"),
            ("tag.gpgSign", "false"),
        ):
            git(root, "config", key, value)
        git(root, "add", "-A")
        git(root, "commit", "-qm", "init")
    return root


def git_tags(root: Path) -> list[str]:
    return git(root, "tag", "--list").stdout.split()


def run_release(
    root: Path, *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(RELEASE), "--root", str(root), *args],
        text=True,
        capture_output=True,
        env=env,
    )


class CheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.root = make_root(self.base)

    def tearDown(self):
        self.tmp.cleanup()

    def test_check_ok_json(self):
        proc = run_release(self.root, "check", "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        data = json.loads(proc.stdout)
        self.assertTrue(data["ok"])
        self.assertEqual(data["version"], "4.4.0")
        self.assertEqual(data["tag"], "v4.4.0")
        self.assertEqual(data["artifact"], "release/KAR-Squad-Bootstrap-v4.4.0.zip")
        self.assertEqual(data["errors"], [])
        self.assertEqual(data["warnings"], [])

    def test_check_dirty_tree_and_allow_dirty(self):
        (self.root / "scratch.txt").write_text("x", encoding="utf-8")
        proc = run_release(self.root, "check")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("RELEASE CHECK: FAIL", proc.stdout)
        self.assertIn("dirty", proc.stdout)

        allowed = run_release(self.root, "check", "--allow-dirty")
        self.assertEqual(allowed.returncode, 0, allowed.stderr + allowed.stdout)
        self.assertIn("RELEASE CHECK: OK", allowed.stdout)
        self.assertIn("WARN", allowed.stdout)
        self.assertIn("dirty", allowed.stdout)

    def test_check_warns_when_version_tag_exists(self):
        git(self.root, "tag", "v4.4.0")
        proc = run_release(self.root, "check", "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        data = json.loads(proc.stdout)
        self.assertTrue(data["ok"])
        self.assertTrue(any("already exists" in item for item in data["warnings"]))

    def test_check_non_git_root_warns_but_passes(self):
        root = make_root(self.base / "nogit", init_git=False)
        proc = run_release(root, "check", "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        data = json.loads(proc.stdout)
        self.assertTrue(data["ok"])
        self.assertTrue(any("not a git repository" in item for item in data["warnings"]))

    def test_check_reports_version_and_changelog_errors(self):
        (self.root / "bootstrap.json").write_text(
            json.dumps({"version": "9.9.9", "config": "missing.md"}) + "\n",
            encoding="utf-8",
        )
        (self.root / "CHANGELOG.md").write_text("# Changelog\n\n## 1.0.0\n", encoding="utf-8")
        proc = run_release(self.root, "check", "--json")
        self.assertEqual(proc.returncode, 1)
        data = json.loads(proc.stdout)
        joined = "\n".join(data["errors"])
        self.assertIn("bootstrap.json version 9.9.9", joined)
        self.assertIn("config handbook", joined)
        self.assertIn("CHANGELOG.md has no", joined)


class PlanTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = make_root(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_plan_lists_steps_in_order(self):
        proc = run_release(self.root, "plan", "--tag", "v4.4.0", "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        data = json.loads(proc.stdout)
        self.assertEqual(
            [step["name"] for step in data["steps"]],
            ["build", "tag", "push", "github-release", "attach"],
        )
        self.assertEqual(data["artifact"], "release/KAR-Squad-Bootstrap-v4.4.0.zip")
        commands = {step["name"]: step["command"] for step in data["steps"]}
        self.assertIn("scripts/build_release.py", commands["build"])
        self.assertIn("git tag -a v4.4.0", commands["tag"])
        self.assertIn("git push origin v4.4.0", commands["push"])
        self.assertIn("gh release create v4.4.0", commands["github-release"])
        self.assertIn("multica issue comment add", commands["attach"])

    def test_plan_rejects_tag_mismatch(self):
        proc = run_release(self.root, "plan", "--tag", "v9.9.9")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("!=", proc.stderr)


class TagTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = make_root(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_tag_requires_approved_by(self):
        proc = run_release(self.root, "tag", "--tag", "v4.4.0")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("approved-by", proc.stderr)
        self.assertEqual(git_tags(self.root), [])

    def test_tag_rejects_mismatch(self):
        proc = run_release(
            self.root, "tag", "--tag", "v9.9.9", "--approved-by", "tester"
        )
        self.assertEqual(proc.returncode, 1)
        self.assertIn("!=", proc.stderr)
        self.assertEqual(git_tags(self.root), [])

    def test_tag_dry_run_prints_only(self):
        proc = run_release(
            self.root, "tag", "--tag", "v4.4.0", "--approved-by", "tester"
        )
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        self.assertIn("DRY-RUN", proc.stdout)
        self.assertIn("git tag -a v4.4.0", proc.stdout)
        self.assertIn("dry-run; not created", proc.stdout)
        self.assertEqual(git_tags(self.root), [])

    def test_tag_apply_without_push_creates_tag(self):
        proc = run_release(
            self.root,
            "tag",
            "--tag",
            "v4.4.0",
            "--approved-by",
            "tester",
            "--apply",
            "--no-push",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        self.assertIn("TAG: v4.4.0 created", proc.stdout)
        self.assertIn("PUSH: skipped", proc.stdout)
        self.assertEqual(git_tags(self.root), ["v4.4.0"])

    def test_tag_apply_rejects_existing_tag(self):
        git(self.root, "tag", "-a", "v4.4.0", "-m", "existing")
        proc = run_release(
            self.root,
            "tag",
            "--tag",
            "v4.4.0",
            "--approved-by",
            "tester",
            "--apply",
        )
        self.assertEqual(proc.returncode, 1)
        self.assertIn("already exists", proc.stderr)


class GitHubReleaseTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.root = make_root(self.base)
        self.artifact = self.root / "release" / "KAR-Squad-Bootstrap-v4.4.0.zip"
        self.artifact.parent.mkdir()
        self.artifact.write_bytes(b"release-zip")
        self.fake = write_fake(self.base, "gh")
        self.log = self.base / "gh.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def env(self, **extra: str) -> dict[str, str]:
        return dict(os.environ, FAKE_LOG=str(self.log), **extra)

    def test_dry_run_prints_gh_command(self):
        proc = run_release(
            self.root,
            "github-release",
            "--tag",
            "v4.4.0",
            "--artifact",
            str(self.artifact),
            "--gh",
            str(self.fake),
            env=self.env(),
        )
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        self.assertIn("DRY-RUN", proc.stdout)
        self.assertIn("gh release create v4.4.0", proc.stdout)
        self.assertIn("--notes-file", proc.stdout)
        self.assertFalse(self.log.exists())

    def test_apply_passes_args_and_prints_url(self):
        url = "https://github.example/releases/v4.4.0"
        proc = run_release(
            self.root,
            "github-release",
            "--tag",
            "v4.4.0",
            "--artifact",
            str(self.artifact),
            "--gh",
            str(self.fake),
            "--apply",
            env=self.env(FAKE_STDOUT=url),
        )
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        self.assertIn(url, proc.stdout)
        lines = self.log.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        args = json.loads(lines[0])
        self.assertEqual(args[:4], ["release", "create", "v4.4.0", str(self.artifact)])
        self.assertEqual(args[args.index("--title") + 1], "KAR Squad OS v4.4.0")
        notes = Path(args[args.index("--notes-file") + 1])
        self.assertTrue(notes.is_file())
        self.assertIn("release item one", notes.read_text(encoding="utf-8"))

    def test_notes_file_can_be_injected(self):
        custom = self.base / "notes.md"
        custom.write_text("custom notes\n", encoding="utf-8")
        proc = run_release(
            self.root,
            "github-release",
            "--tag",
            "v4.4.0",
            "--artifact",
            str(self.artifact),
            "--gh",
            str(self.fake),
            "--notes-file",
            str(custom),
            env=self.env(),
        )
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        self.assertIn(str(custom), proc.stdout)

    def test_gh_failure_exits_one(self):
        proc = run_release(
            self.root,
            "github-release",
            "--tag",
            "v4.4.0",
            "--artifact",
            str(self.artifact),
            "--gh",
            str(self.fake),
            "--apply",
            env=self.env(FAKE_EXIT="1"),
        )
        self.assertEqual(proc.returncode, 1)
        self.assertIn("GITHUB RELEASE: FAIL", proc.stderr)


class AttachTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.root = make_root(self.base)
        self.artifact = self.base / "KAR-Squad-Bootstrap-v4.4.0.zip"
        self.artifact.write_bytes(b"release-artifact")
        self.fake = write_fake(self.base, "multica")
        self.log = self.base / "multica.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def env(self, **extra: str) -> dict[str, str]:
        return dict(os.environ, FAKE_LOG=str(self.log), **extra)

    def test_dry_run_uses_content_file(self):
        proc = run_release(
            self.root,
            "attach",
            "--issue",
            "KAR-13",
            "--artifact",
            str(self.artifact),
            "--tag",
            "v4.4.0",
            "--multica",
            str(self.fake),
            env=self.env(),
        )
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        self.assertIn("multica issue comment add KAR-13", proc.stdout)
        self.assertIn("--content-file", proc.stdout)
        self.assertIn("--attachment", proc.stdout)
        self.assertFalse(self.log.exists())
        release_dir = self.root / "release"
        self.assertFalse(release_dir.exists() and any(release_dir.iterdir()))

    def test_apply_writes_body_and_logs_command(self):
        proc = run_release(
            self.root,
            "attach",
            "--issue",
            "KAR-13",
            "--artifact",
            str(self.artifact),
            "--tag",
            "v4.4.0",
            "--multica",
            str(self.fake),
            "--apply",
            "--approved-by",
            "tester",
            env=self.env(FAKE_STDOUT="comment-1"),
        )
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        self.assertIn("comment-1", proc.stdout)
        args = json.loads(self.log.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(args[:4], ["issue", "comment", "add", "KAR-13"])
        self.assertNotIn("--content", args)
        body = Path(args[args.index("--content-file") + 1])
        self.assertTrue(body.is_file())
        text = body.read_text(encoding="utf-8")
        self.assertIn("v4.4.0", text)
        self.assertIn(self.artifact.name, text)
        self.assertIn(hashlib.sha256(b"release-artifact").hexdigest(), text)
        self.assertIn("发布由 tester 批准", text)

    def test_missing_artifact_fails(self):
        proc = run_release(
            self.root,
            "attach",
            "--issue",
            "KAR-13",
            "--artifact",
            str(self.base / "missing.zip"),
            "--tag",
            "v4.4.0",
            "--multica",
            str(self.fake),
            env=self.env(),
        )
        self.assertEqual(proc.returncode, 1)
        self.assertIn("does not exist", proc.stderr)


class PublishTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.root = make_root(self.base)
        self.gh = write_fake(self.base, "gh")
        self.multica = write_fake(self.base, "multica")
        self.gh_log = self.base / "gh.jsonl"
        self.multica_log = self.base / "multica.jsonl"
        self.artifact = self.root / "release" / "KAR-Squad-Bootstrap-v4.4.0.zip"
        self.build = self.root / "scripts" / "build_release.py"
        self.build.write_text(
            "from pathlib import Path\n"
            f"p = Path({str(self.artifact)!r})\n"
            "p.parent.mkdir(parents=True, exist_ok=True)\n"
            "p.write_bytes(b'built-zip')\n"
            "print('BUILT')\n",
            encoding="utf-8",
        )
        git(self.root, "add", str(self.build))
        git(self.root, "commit", "-qm", "add build stub")

    def tearDown(self):
        self.tmp.cleanup()

    def env(self, **extra: str) -> dict[str, str]:
        return dict(
            os.environ,
            FAKE_LOG=str(self.gh_log),
            FAKE_STDOUT="https://github.example/releases/v4.4.0",
            **extra,
        )

    def test_dry_run_has_no_side_effects(self):
        proc = run_release(
            self.root,
            "publish",
            "--tag",
            "v4.4.0",
            "--issue",
            "KAR-13",
            "--approved-by",
            "tester",
            "--gh",
            str(self.gh),
            "--multica",
            str(self.multica),
            env=self.env(),
        )
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        for marker in (
            "[1/5] check",
            "[2/5] build",
            "[3/5] tag",
            "[4/5] github-release",
            "[5/5] attach",
            "python3 scripts/build_release.py",
            "git tag -a v4.4.0",
            "gh release create v4.4.0",
            "multica issue comment add KAR-13",
            "dry-run only",
        ):
            self.assertIn(marker, proc.stdout)
        self.assertEqual(git_tags(self.root), [])
        self.assertFalse((self.root / "release").exists())
        self.assertFalse(self.gh_log.exists())
        self.assertFalse(self.multica_log.exists())

    def test_missing_approved_by_fails(self):
        proc = run_release(
            self.root,
            "publish",
            "--tag",
            "v4.4.0",
            "--issue",
            "KAR-13",
            "--gh",
            str(self.gh),
            "--multica",
            str(self.multica),
            env=self.env(),
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("approved-by", proc.stderr)
        self.assertEqual(git_tags(self.root), [])
        self.assertFalse(self.gh_log.exists())
        self.assertFalse(self.multica_log.exists())

    def test_apply_builds_tags_releases_and_attaches(self):
        # Multica fake gets its own log so it does not collide with gh.
        env = dict(self.env(), FAKE_LOG=str(self.gh_log))
        proc = subprocess.run(
            [
                sys.executable,
                str(RELEASE),
                "--root",
                str(self.root),
                "publish",
                "--tag",
                "v4.4.0",
                "--issue",
                "KAR-13",
                "--approved-by",
                "tester",
                "--apply",
                "--no-push",
                "--gh",
                str(self.gh),
                "--multica",
                str(self.multica),
            ],
            text=True,
            capture_output=True,
            env=env,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        self.assertIn("PUBLISH: OK", proc.stdout)
        self.assertEqual(git_tags(self.root), ["v4.4.0"])
        self.assertTrue(self.artifact.is_file())
        gh_args = json.loads(self.gh_log.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(
            gh_args[:4],
            ["release", "create", "v4.4.0", str(self.artifact.resolve())],
        )
        # The multica fake appends to the same FAKE_LOG, so the second line is attach.
        all_lines = self.gh_log.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(all_lines), 2)
        multica_args = json.loads(all_lines[1])
        self.assertEqual(multica_args[:4], ["issue", "comment", "add", "KAR-13"])


if __name__ == "__main__":
    unittest.main()
