#!/usr/bin/env python3
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts/human_wip.py"
NOW = "2026-11-09T12:00:00Z"


def write_manifest(root, issue, gates, owner="alice"):
    directory = root / issue
    directory.mkdir(parents=True)
    data = {
        "version": 2,
        "change_set_id": issue,
        "issue": issue,
        "slug": "wip",
        "decision_owner": owner,
        "gates": gates,
    }
    path = directory / "delivery-manifest.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def pending(gate, requested_at, **extra):
    data = {"status": "pending", "requested_at": requested_at}
    data.update(extra)
    return data


def run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], text=True, capture_output=True)


class HumanWipTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        write_manifest(self.root, "KAR-31", {
            "h1": pending("h1", "2026-11-08T00:00:00Z"),
            "h2": pending("h2", "2026-11-09T00:00:00Z"),
            "h3": pending("h3", "2026-11-09T06:00:00Z"),
        })

    def tearDown(self):
        self.tmp.cleanup()

    def check(self, *extra):
        return run("check", "--manifests", str(self.root), "--now", NOW, "--json", *extra)

    def test_third_pending_gate_is_queued(self):
        proc = self.check()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        alice = report["owners"]["alice"]
        self.assertEqual(alice["pending"], 3)
        self.assertEqual(alice["over_limit"], 1)
        self.assertEqual(len(alice["active"]), 2)
        self.assertEqual(len(alice["queued"]), 1)
        self.assertEqual(alice["queued"][0]["gate"], "h3")
        self.assertEqual(report["totals"]["queued"], 1)

    def test_reminder_due_once(self):
        report = json.loads(self.check().stdout)
        due = report["owners"]["alice"]["reminders_due"]
        self.assertEqual([item["gate"] for item in due], ["h1"])
        self.assertEqual(report["totals"]["reminders_due"], 1)

    def test_reminder_sent_stops_further_reminders(self):
        write_manifest(self.root, "KAR-32", {
            "h1": pending("h1", "2026-11-08T00:00:00Z", reminder_sent_at="2026-11-09T01:00:00Z", reminder_count=1),
        })
        report = json.loads(self.check().stdout)
        self.assertEqual(report["totals"]["reminders_due"], 1)
        self.assertEqual(report["totals"]["after_reminder_waiting"], 1)

    def test_agent_approval_is_a_violation(self):
        write_manifest(self.root, "KAR-33", {
            "h1": {
                "status": "approved",
                "requested_at": "2026-11-08T00:00:00Z",
                "approved_at": "2026-11-08T01:00:00Z",
                "approved_by": "KAR-01-Lead",
                "approver_type": "agent",
            },
        })
        proc = self.check()
        self.assertNotEqual(proc.returncode, 0)
        report = json.loads(proc.stdout)
        self.assertTrue(any("not human" in item for item in report["violations"]))


if __name__ == "__main__":
    unittest.main()
