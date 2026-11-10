#!/usr/bin/env python3
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts/generate.py"
TARGETS = (
    "skills.json",
    "agents.json",
    "squad/KAR-Delivery-Squad.json",
    "bootstrap.json",
    "skills/kar-squad-profile/squad.json",
)


def run(root, *args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root), *args],
        text=True,
        capture_output=True,
    )


def minimal_source(version="4.4.0"):
    return {
        "kit": {
            "name": "Test Squad",
            "version": version,
            "bootstrap_profile": f"Test-Bootstrap-v{version}",
            "config": "config/Test.md",
            "requires": {"python": "3.9+"},
            "squad_file": "squad/Test.json",
            "squad_instructions": "squad/Test.md",
            "init_template": "skills/kar-x/templates/p.md",
            "notes": ["test"],
        },
        "skills": [
            {"name": "kar-x", "description": "x", "path": "skills/kar-x/SKILL.md"},
        ],
        "agents": [
            {"name": "KAR-01", "description": "lead", "runtime_env": "R", "max": 2, "skills": ["kar-x"]},
        ],
        "squad": {
            "name": "Test Squad",
            "leader": "KAR-01",
            "members": [{"name": "KAR-01", "role": "lead"}],
        },
        "defaults": {
            "required_project_fields": ["repos"],
            "allowed_project_fields": ["repos"],
            "squad_invariants": ["human_gates"],
            "lanes": {"quick": {"human_gates": 1}},
        },
    }


class GenerateRepoTest(unittest.TestCase):
    def test_repo_is_in_sync_with_source(self):
        proc = run(ROOT, "--check")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("GENERATE: OK", proc.stdout)

    def test_all_generated_files_exist(self):
        for path in TARGETS:
            self.assertTrue((ROOT / path).exists(), path)

    def test_generated_bootstrap_matches_version(self):
        version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        bootstrap = json.loads((ROOT / "bootstrap.json").read_text(encoding="utf-8"))
        self.assertEqual(bootstrap["version"], version)
        self.assertEqual(bootstrap["config"], "config/KAR-Squad-Config-v4.4.md")
        profile = json.loads((ROOT / "skills/kar-squad-profile/squad.json").read_text(encoding="utf-8"))
        self.assertEqual(profile["version"], version)


class GenerateTempRootTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "sources").mkdir()
        (self.root / "sources/squad.json").write_text(
            json.dumps(minimal_source(), ensure_ascii=False), encoding="utf-8"
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_check_fails_then_write_then_check_passes(self):
        before = run(self.root, "--check")
        self.assertEqual(before.returncode, 1)
        self.assertIn("missing", before.stdout)
        written = run(self.root, "--write")
        self.assertEqual(written.returncode, 0, written.stdout + written.stderr)
        after = run(self.root, "--check")
        self.assertEqual(after.returncode, 0, after.stdout + after.stderr)
        profile = json.loads((self.root / "skills/kar-squad-profile/squad.json").read_text(encoding="utf-8"))
        self.assertEqual(profile["version"], "4.4.0")
        self.assertEqual(profile["lanes"]["quick"]["human_gates"], 1)

    def test_drift_is_detected(self):
        run(self.root, "--write")
        agents_path = self.root / "agents.json"
        data = json.loads(agents_path.read_text(encoding="utf-8"))
        data[0]["max"] = 5
        agents_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        proc = run(self.root, "--check")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("agents.json", proc.stdout)
        self.assertIn("drift", proc.stdout)

    def test_json_output_is_machine_readable(self):
        run(self.root, "--write")
        proc = run(self.root, "--check", "--json")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["ok"])

    def test_duplicate_skill_is_rejected(self):
        source = minimal_source()
        source["skills"].append({"name": "kar-x", "description": "dup", "path": "skills/x.md"})
        (self.root / "sources/squad.json").write_text(json.dumps(source), encoding="utf-8")
        proc = run(self.root, "--write")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("duplicate", proc.stdout)

    def test_unknown_agent_binding_is_rejected(self):
        source = minimal_source()
        source["agents"][0]["skills"] = ["kar-missing"]
        (self.root / "sources/squad.json").write_text(json.dumps(source), encoding="utf-8")
        proc = run(self.root, "--write")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("unknown skill", proc.stdout)

    def test_bad_version_is_rejected(self):
        source = minimal_source(version="4.4")
        (self.root / "sources/squad.json").write_text(json.dumps(source), encoding="utf-8")
        proc = run(self.root, "--write")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("kit.version", proc.stdout)


if __name__ == "__main__":
    unittest.main()
