#!/usr/bin/env python3
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts/metrics.py"


def write_manifest(root, issue, closed_at, metrics, approved_at=None):
    directory = root / issue
    directory.mkdir(parents=True)
    data = {
        "version": 2,
        "change_set_id": issue,
        "issue": issue,
        "slug": "metrics",
        "metrics": dict(metrics, closed_at=closed_at),
        "gates": {
            "h1": {"status": "approved", "requested_at": "2026-10-26T00:00:00Z"},
            "h3": {"status": "approved", "approved_at": approved_at or closed_at},
        },
    }
    path = directory / "delivery-manifest.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], text=True, capture_output=True)


BASE_METRICS = {
    "human_touches": 3,
    "wait_human": 4.0,
    "rework_rounds": 1,
    "candidate_recuts": 2,
    "escaped_defects": 0,
    "cycle_time_hours": 20.0,
}


class MetricsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        write_manifest(self.root, "KAR-21", "2026-11-02T10:00:00Z", BASE_METRICS)
        write_manifest(self.root, "KAR-22", "2026-11-03T10:00:00Z", dict(BASE_METRICS, human_touches=2, wait_human=8.0))
        write_manifest(self.root, "KAR-23", "2026-11-09T10:00:00Z", dict(BASE_METRICS, escaped_defects=1))

    def tearDown(self):
        self.tmp.cleanup()

    def test_json_report_has_five_metrics_and_weekly_six(self):
        proc = run("report", "--manifests", str(self.root), "--format", "json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        self.assertEqual(len(report["per_issue"]), 3)
        first = report["per_issue"][0]
        for key in ("human_touches", "wait_human", "rework_rounds", "candidate_recuts", "escaped_defects"):
            self.assertIn(key, first["metrics"])
        self.assertIn("cycle_time_hours", first)
        self.assertEqual(len(report["weeks"]), 2)
        week = report["weeks"][0]
        self.assertEqual(week["week"], "2026-W45")
        self.assertEqual(week["human_touches"], 5)
        self.assertEqual(week["wait_human"], 6.0)
        self.assertIn("cycle_time_hours", week)
        self.assertTrue(report["baseline"]["ready"])
        self.assertEqual(report["baseline"]["weeks_collected"], 2)

    def test_week_filter(self):
        proc = run("report", "--manifests", str(self.root), "--week", "2026-W45", "--format", "json")
        report = json.loads(proc.stdout)
        self.assertEqual(len(report["weeks"]), 1)
        self.assertEqual(report["weeks"][0]["week"], "2026-W45")

    def test_missing_metrics_mark_incomplete_and_strict_fails(self):
        bad = write_manifest(self.root, "KAR-24", "2026-11-10T10:00:00Z", {"human_touches": 1})
        proc = run("report", "--manifests", str(self.root), "--format", "json", "--strict")
        self.assertNotEqual(proc.returncode, 0)
        report = json.loads(proc.stdout)
        issues = {item["issue"] for item in report["incomplete"]}
        self.assertIn("KAR-24", issues)
        self.assertTrue(bad.exists())

    def test_cycle_time_derived_from_gates(self):
        data = {
            "version": 2,
            "issue": "KAR-25",
            "slug": "derived",
            "metrics": {
                "human_touches": 3,
                "wait_human": 4,
                "rework_rounds": 0,
                "candidate_recuts": 0,
                "escaped_defects": 0,
            },
            "gates": {
                "h1": {"status": "approved", "requested_at": "2026-11-01T00:00:00Z"},
                "h3": {"status": "approved", "approved_at": "2026-11-02T02:00:00Z"},
            },
        }
        directory = self.root / "KAR-25"
        directory.mkdir()
        (directory / "delivery-manifest.json").write_text(json.dumps(data), encoding="utf-8")
        proc = run("report", "--manifests", str(self.root), "--format", "json")
        report = json.loads(proc.stdout)
        entry = next(item for item in report["per_issue"] if item["issue"] == "KAR-25")
        self.assertEqual(entry["cycle_time_hours"], 26.0)
        self.assertEqual(entry["week"], "2026-W45")

    def test_markdown_report_mentions_baseline(self):
        proc = run("report", "--manifests", str(self.root))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("每周 6 指标", proc.stdout)
        self.assertIn("基线段", proc.stdout)


if __name__ == "__main__":
    unittest.main()
