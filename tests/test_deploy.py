#!/usr/bin/env python3
"""Tests for scripts/deploy.py using injectable stub bootstrap/verify scripts."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEPLOY = ROOT / "scripts/deploy.py"

STUB = '''#!/usr/bin/env python3
import json
import os
import sys

args = sys.argv[1:]
log = os.environ.get("STUB_LOG")
if log:
    with open(log, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(args, ensure_ascii=False) + "\\n")
if "--apply" in args:
    mode = "apply"
    code = int(os.environ.get("STUB_APPLY_EXIT", "0"))
elif "--dry-run" in args:
    mode = "dry-run"
    code = int(os.environ.get("STUB_DRYRUN_EXIT", "0"))
else:
    mode = "verify"
    code = int(os.environ.get("STUB_VERIFY_EXIT", "0"))
print("stub " + mode)
if code:
    print("stub failure", file=sys.stderr)
sys.exit(code)
'''


def make_root(base: Path, version: str = "4.4.0", bootstrap_version: str | None = None) -> Path:
    root = base / "repo"
    root.mkdir(parents=True)
    (root / "VERSION").write_text(version + "\n", encoding="utf-8")
    (root / "bootstrap.json").write_text(
        json.dumps(
            {
                "version": bootstrap_version or version,
                "config": f"config/KAR-Squad-Config-v{version}.md",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "config").mkdir()
    (root / "config" / f"KAR-Squad-Config-v{version}.md").write_text(
        "# config\n", encoding="utf-8"
    )
    scripts = root / "scripts"
    scripts.mkdir()
    (scripts / "bootstrap.py").write_text(STUB, encoding="utf-8")
    (scripts / "verify.py").write_text(STUB, encoding="utf-8")
    return root


def run_deploy(
    root: Path, *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(DEPLOY), "--root", str(root), *args],
        text=True,
        capture_output=True,
        env=env,
    )


def read_log(path: Path) -> list[list[str]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


class DeployTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.root = make_root(self.base)
        self.log = self.base / "calls.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def env(self, **extra: str) -> dict[str, str]:
        return dict(os.environ, STUB_LOG=str(self.log), **extra)

    def common_args(self) -> list[str]:
        return [
            "--multica",
            "fake-multica",
            "--workspace-id",
            "ws-1",
            "--core-runtime",
            "core-1",
            "--qa-runtime",
            "qa-1",
            "--profile",
            "ci",
            "--backup-dir",
            "backups",
        ]

    def test_dry_run_calls_only_bootstrap_dry_run(self):
        proc = run_deploy(self.root, *self.common_args(), env=self.env())
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        calls = read_log(self.log)
        self.assertEqual(len(calls), 1)
        args = calls[0]
        self.assertIn("--dry-run", args)
        self.assertNotIn("--apply", args)
        self.assertNotIn("--update", args)
        self.assertEqual(args[args.index("--multica") + 1], "fake-multica")
        self.assertEqual(args[args.index("--workspace-id") + 1], "ws-1")
        self.assertEqual(args[args.index("--core-runtime") + 1], "core-1")
        self.assertEqual(args[args.index("--qa-runtime") + 1], "qa-1")
        self.assertEqual(args[args.index("--backup-dir") + 1], "backups")
        self.assertIn(
            "dry-run only; re-run with --apply --approved-by <human> to write",
            proc.stdout,
        )
        self.assertIn("skipped", proc.stdout)

    def test_apply_requires_approved_by(self):
        proc = run_deploy(self.root, "--apply", *self.common_args(), env=self.env())
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("approved-by", proc.stderr + proc.stdout)
        self.assertEqual(read_log(self.log), [])

    def test_apply_runs_bootstrap_with_update_then_verify(self):
        proc = run_deploy(
            self.root,
            "--apply",
            "--approved-by",
            "tester",
            *self.common_args(),
            env=self.env(),
        )
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        calls = read_log(self.log)
        self.assertEqual(len(calls), 3)
        dry_run, bootstrap, verify = calls
        self.assertIn("--dry-run", dry_run)
        self.assertIn("--apply", bootstrap)
        self.assertIn("--update", bootstrap)
        self.assertNotIn("--dry-run", bootstrap)
        self.assertNotIn("--dry-run", verify)
        self.assertNotIn("--apply", verify)
        self.assertEqual(verify[verify.index("--multica") + 1], "fake-multica")
        self.assertEqual(verify[verify.index("--workspace-id") + 1], "ws-1")
        self.assertEqual(verify[verify.index("--profile") + 1], "ci")
        self.assertIn("STEP", proc.stdout)
        self.assertIn("version: 4.4.0", proc.stdout)
        self.assertIn("deployed: yes", proc.stdout)

    def test_apply_no_update_omits_update_flag(self):
        proc = run_deploy(
            self.root,
            "--apply",
            "--approved-by",
            "tester",
            "--no-update",
            *self.common_args(),
            env=self.env(),
        )
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        calls = read_log(self.log)
        self.assertEqual(len(calls), 3)
        self.assertNotIn("--update", calls[1])

    def test_verify_failure_exits_one_and_reports_step(self):
        proc = run_deploy(
            self.root,
            "--apply",
            "--approved-by",
            "tester",
            *self.common_args(),
            env=self.env(STUB_VERIFY_EXIT="1"),
        )
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(len(read_log(self.log)), 3)
        self.assertIn("verify", proc.stderr)
        self.assertIn("DEPLOY: FAIL", proc.stderr)
        self.assertIn("failed", proc.stdout)

    def test_bootstrap_failure_stops_before_verify(self):
        proc = run_deploy(
            self.root,
            "--apply",
            "--approved-by",
            "tester",
            *self.common_args(),
            env=self.env(STUB_APPLY_EXIT="1"),
        )
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(len(read_log(self.log)), 2)
        self.assertIn("bootstrap apply", proc.stderr)
        self.assertIn("skipped", proc.stdout)

    def test_version_mismatch_fails_before_any_call(self):
        root = make_root(self.base / "mismatch", bootstrap_version="9.9.9")
        log = self.base / "mismatch-calls.jsonl"
        proc = run_deploy(
            root,
            "--apply",
            "--approved-by",
            "tester",
            *self.common_args(),
            env=dict(os.environ, STUB_LOG=str(log)),
        )
        self.assertEqual(proc.returncode, 1)
        self.assertIn("bootstrap.json version 9.9.9", proc.stderr + proc.stdout)
        self.assertEqual(read_log(log), [])

    def test_json_output_is_machine_readable(self):
        proc = run_deploy(
            self.root, *self.common_args(), "--json", env=self.env()
        )
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        data = json.loads(proc.stdout)
        self.assertTrue(data["ok"])
        self.assertTrue(data["dry_run"])
        self.assertEqual(data["version"], "4.4.0")
        self.assertEqual(
            [step["status"] for step in data["steps"]],
            ["ok", "ok", "skipped", "skipped"],
        )
        self.assertEqual(len(read_log(self.log)), 1)


if __name__ == "__main__":
    unittest.main()
