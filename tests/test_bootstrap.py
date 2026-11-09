#!/usr/bin/env python3
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAKE = ROOT / "tests/fake_multica.py"
BOOTSTRAP = ROOT / "scripts/bootstrap.py"


class BootstrapDryRunTest(unittest.TestCase):
    def test_dry_run_creates_and_uploads_files(self):
        os.chmod(FAKE, 0o755)
        with tempfile.TemporaryDirectory() as td:
            log = Path(td) / "calls.jsonl"
            env = dict(os.environ, FAKE_LOG=str(log))
            proc = subprocess.run(
                [
                    sys.executable, str(BOOTSTRAP), "--dry-run",
                    "--multica", str(FAKE),
                    "--workspace-id", "ws",
                    "--core-runtime", "core",
                ],
                text=True, capture_output=True, env=env,
            )
            log_exists = log.exists()
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        self.assertIn("skill files upsert", proc.stdout)
        self.assertIn("DRY-RUN summary", proc.stdout)
        self.assertIn("agents created=8", proc.stdout)
        self.assertTrue(log_exists)


if __name__ == "__main__":
    unittest.main()


class BootstrapBackupTest(unittest.TestCase):
    def test_backup_includes_skill_files_and_details(self):
        os.chmod(FAKE, 0o755)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state = root / "state.json"
            state.write_text(__import__("json").dumps({
                "skills": [{"id": "s1", "name": "kar-constitution", "description": "old"}],
                "skill_details": {"s1": {"id": "s1", "name": "kar-constitution", "description": "old", "content": "# old"}},
                "skill_files": {"s1": [{"path": "notes.md", "content": "note"}]},
            }), encoding="utf-8")
            backup_dir = root / "backups"
            env = dict(os.environ, FAKE_LOG=str(root / "calls.jsonl"), FAKE_STATE=str(state))
            proc = subprocess.run(
                [
                    sys.executable, str(BOOTSTRAP), "--apply",
                    "--multica", str(FAKE),
                    "--workspace-id", "ws",
                    "--core-runtime", "core",
                    "--backup-dir", str(backup_dir),
                ],
                text=True, capture_output=True, env=env,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
            files = list(backup_dir.glob("backup-*.json"))
            self.assertEqual(len(files), 1)
            data = __import__("json").loads(files[0].read_text(encoding="utf-8"))
            skill = next(item for item in data["skills"] if item["name"] == "kar-constitution")
            self.assertEqual(skill["files"][0]["path"], "notes.md")
            self.assertEqual(skill["content"], "# old")
