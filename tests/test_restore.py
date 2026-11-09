#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts/restore.py"
FAKE = ROOT / "tests/fake_multica.py"


def backup():
    return {
        "version": "4.2.0",
        "created_at": "2026-11-09T00:00:00Z",
        "skills": [{
            "id": "old-s1",
            "name": "kar-constitution",
            "description": "宪法",
            "content": "# constitution",
            "files": [{"path": "notes.md", "content": "note"}],
        }],
        "agents": [
            {
                "id": "old-a1",
                "name": "KAR-01-Lead",
                "description": "Lead",
                "instructions": "# lead",
                "max_concurrent_tasks": 6,
                "runtime_id": "rt-core",
                "skills": [{"id": "old-s1", "name": "kar-constitution"}],
            },
            {
                "id": "old-a2",
                "name": "KAR-06-Reviewer",
                "description": "Reviewer",
                "instructions": "# reviewer",
                "max_concurrent_tasks": 3,
                "runtime_id": "rt-core",
                "skills": [{"id": "old-s1", "name": "kar-constitution"}],
            },
        ],
        "squad": {
            "id": "old-sq",
            "name": "KAR Delivery Squad",
            "description": "squad",
            "instructions": "# squad",
            "leader_id": "old-a1",
        },
        "squad_members": [
            {"member_id": "old-a1", "member_type": "agent", "role": "leader"},
            {"member_id": "old-a2", "member_type": "agent", "role": "reviewer"},
        ],
    }


class RestoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.backup_path = self.root / "backup.json"
        self.backup_path.write_text(json.dumps(backup(), ensure_ascii=False), encoding="utf-8")
        self.log = self.root / "calls.jsonl"
        os.chmod(FAKE, 0o755)

    def tearDown(self):
        self.tmp.cleanup()

    def run_restore(self, *extra, state=None):
        env = dict(os.environ, FAKE_LOG=str(self.log))
        if state is not None:
            state_path = self.root / "state.json"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            env["FAKE_STATE"] = str(state_path)
        return subprocess.run(
            [
                sys.executable, str(SCRIPT),
                "--backup", str(self.backup_path),
                "--multica", str(FAKE),
                "--workspace-id", "ws",
                *extra,
            ],
            text=True, capture_output=True, env=env,
        )

    def calls(self):
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines() if line.strip()]

    def test_dry_run_writes_nothing(self):
        proc = self.run_restore()
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        self.assertIn("would create skill: kar-constitution", proc.stdout)
        self.assertIn("would create agent: KAR-01-Lead", proc.stdout)
        self.assertIn("would create squad: KAR Delivery Squad", proc.stdout)
        writes = [call for call in self.calls() if any(word in call for word in ("create", "update", "upsert", "set-role", "skills"))]
        self.assertEqual(writes, [])

    def test_apply_creates_skills_agents_squad_and_files(self):
        proc = self.run_restore("--apply")
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        calls = self.calls()
        flattened = [" ".join(call) for call in calls]
        self.assertTrue(any("skill create" in call for call in flattened))
        self.assertTrue(any("skill files upsert" in call for call in flattened))
        self.assertTrue(any("agent create" in call for call in flattened))
        self.assertTrue(any("agent skills set" in call for call in flattened))
        self.assertTrue(any("squad create" in call for call in flattened))
        self.assertTrue(any("squad member add" in call for call in flattened))
        self.assertEqual(sum(1 for call in flattened if "squad member add" in call), 1)
        self.assertIn("RESTORE: done", proc.stdout)

    def test_apply_updates_existing_objects(self):
        state = {
            "skills": [{"id": "s1", "name": "kar-constitution", "description": "old"}],
            "skill_details": {"s1": {"id": "s1", "name": "kar-constitution", "description": "old", "content": "# old"}},
            "agents": [{"id": "a1", "name": "KAR-01-Lead"}, {"id": "a2", "name": "KAR-06-Reviewer"}],
            "agent_details": {
                "a1": {"id": "a1", "name": "KAR-01-Lead"},
                "a2": {"id": "a2", "name": "KAR-06-Reviewer"},
            },
            "squads": [{"id": "sq", "name": "KAR Delivery Squad"}],
            "squad_details": {
                "sq": {"id": "sq", "name": "KAR Delivery Squad", "leader_id": "a1"},
            },
            "squad_members": [
                {"member_id": "a1", "member_type": "agent", "role": "leader"},
                {"member_id": "a2", "member_type": "agent", "role": "member"},
            ],
        }
        proc = self.run_restore("--apply", state=state)
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        flattened = [" ".join(call) for call in self.calls()]
        self.assertTrue(any("skill update" in call for call in flattened))
        self.assertTrue(any("agent update" in call for call in flattened))
        self.assertTrue(any("squad update" in call for call in flattened))
        self.assertTrue(any("squad member set-role" in call for call in flattened))
        self.assertFalse(any("skill create" in call for call in flattened))
        self.assertFalse(any("agent create" in call for call in flattened))
        self.assertFalse(any("squad create" in call for call in flattened))

    def test_missing_backup_fails(self):
        self.backup_path.unlink()
        proc = self.run_restore()
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("backup not found", proc.stderr)


if __name__ == "__main__":
    unittest.main()
