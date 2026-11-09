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
