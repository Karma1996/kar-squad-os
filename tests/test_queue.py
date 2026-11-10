#!/usr/bin/env python3
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts/queue.py"
NOW = "2026-11-10T09:00:00Z"


def item(item_id, issue, lane, severity, **extra):
    data = {"id": item_id, "issue": issue, "lane": lane, "severity": severity}
    data.update(extra)
    return data


def running(item_id, issue, lane, severity, started_at="2026-11-10T08:00:00Z"):
    return item(item_id, issue, lane, severity, started_at=started_at)


def queued(item_id, issue, lane, severity, enqueued_at="2026-11-10T08:30:00Z", **extra):
    return item(item_id, issue, lane, severity, enqueued_at=enqueued_at, **extra)


def run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], text=True, capture_output=True)


class QueueTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, data):
        path = self.root / "queue.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def check(self, data):
        return run("check", "--queue", str(self.write(data)))

    def plan(self, data, *extra):
        return run("plan", "--queue", str(self.write(data)), *extra)

    def plan_json(self, data, *extra):
        proc = self.plan(data, "--json", *extra)
        return proc, json.loads(proc.stdout)

    def test_s0_preempts_running_non_s0_and_wins_over_s1(self):
        data = {
            "now": NOW,
            "running": [running("run-1", "KAR-2", "standard", "S3")],
            "queued": [
                queued("q-s1", "KAR-3", "quick", "S1", "2026-11-10T08:00:00Z"),
                queued("q-s0", "KAR-4", "quick", "S0", "2026-11-10T08:40:00Z"),
            ],
        }
        proc, report = self.plan_json(data)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(report["ok"])
        self.assertEqual([entry["id"] for entry in report["dispatch"]], ["q-s0", "q-s1"])
        self.assertEqual(len(report["preemptions"]), 1)
        preemption = report["preemptions"][0]
        self.assertEqual(preemption["running_id"], "run-1")
        self.assertEqual(preemption["by_queued_id"], "q-s0")
        self.assertIn("S0 抢占", preemption["reason"])
        self.assertIn("S0 抢占", report["dispatch"][0]["reason"])

    def test_s1_preempts_running_s2_on_any_lane(self):
        data = {
            "now": NOW,
            "running": [running("run-1", "KAR-2", "program", "S2")],
            "queued": [queued("q-1", "KAR-3", "standard", "S1")],
        }
        proc, report = self.plan_json(data)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(len(report["preemptions"]), 1)
        self.assertEqual(report["preemptions"][0]["by_queued_id"], "q-1")
        self.assertIn("S1 抢占", report["preemptions"][0]["reason"])

    def test_s1_does_not_preempt_s1_and_s0_is_never_preempted(self):
        data = {
            "now": NOW,
            "running": [
                running("run-1", "KAR-1", "standard", "S0"),
                running("run-2", "KAR-2", "standard", "S1"),
            ],
            "queued": [queued("q-1", "KAR-3", "quick", "S1")],
        }
        proc, report = self.plan_json(data)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(report["preemptions"], [])

    def test_dispatch_open_program_window_before_quick_fifo(self):
        data = {
            "now": NOW,
            "running": [],
            "queued": [
                queued("q-quick-early", "KAR-10", "quick", "S2", "2026-11-10T08:00:00Z"),
                queued(
                    "q-prog-window", "KAR-11", "program", "S2", "2026-11-10T08:30:00Z",
                    program_merge_window={
                        "open_at": "2026-11-10T08:45:00Z",
                        "close_at": "2026-11-10T12:00:00Z",
                    },
                ),
                queued("q-quick-late", "KAR-12", "quick", "S2", "2026-11-10T08:10:00Z"),
            ],
        }
        proc = self.plan(data)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Program 合并窗口开放（12:00 关闭）", proc.stdout)
        self.assertIn("Quick FIFO", proc.stdout)
        report = json.loads(self.plan(data, "--json").stdout)
        self.assertEqual(
            [entry["id"] for entry in report["dispatch"]],
            ["q-prog-window", "q-quick-early", "q-quick-late"],
        )

    def test_closed_merge_window_is_not_prioritized(self):
        data = {
            "now": NOW,
            "running": [],
            "queued": [
                queued("q-quick", "KAR-21", "quick", "S2", "2026-11-10T08:00:00Z"),
                queued(
                    "q-prog-closed", "KAR-20", "program", "S2", "2026-11-10T08:10:00Z",
                    program_merge_window={
                        "open_at": "2026-11-10T07:00:00Z",
                        "close_at": "2026-11-10T08:30:00Z",
                    },
                ),
            ],
        }
        proc, report = self.plan_json(data)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(report["ok"])
        self.assertEqual([entry["id"] for entry in report["dispatch"]], ["q-quick", "q-prog-closed"])
        self.assertEqual(report["dispatch"][1]["reason"], "窗口已关闭，按入队时间")
        self.assertTrue(any("窗口已关闭" in warning for warning in report["warnings"]))

    def test_invalid_queue_fails_with_path_like_errors(self):
        cases = {
            "severity": (
                [queued("q-1", "KAR-3", "quick", "S5")],
                "queued[0].severity",
            ),
            "duplicate_id": (
                [queued("run-1", "KAR-3", "quick", "S2")],
                "duplicate id run-1",
            ),
            "window_on_quick": (
                [queued(
                    "q-1", "KAR-3", "quick", "S2",
                    program_merge_window={
                        "open_at": "2026-11-10T08:00:00Z",
                        "close_at": "2026-11-10T09:00:00Z",
                    },
                )],
                "only allowed on lane=program",
            ),
            "window_close_before_open": (
                [queued(
                    "q-1", "KAR-3", "program", "S2",
                    program_merge_window={
                        "open_at": "2026-11-10T10:00:00Z",
                        "close_at": "2026-11-10T09:00:00Z",
                    },
                )],
                "close_at must be after open_at",
            ),
            "bad_timestamp": (
                [queued("q-1", "KAR-3", "quick", "S2", enqueued_at="yesterday")],
                "queued[0].enqueued_at",
            ),
        }
        for name, (queue, expected) in cases.items():
            with self.subTest(name=name):
                data = {
                    "now": NOW,
                    "running": [running("run-1", "KAR-2", "standard", "S3")],
                    "queued": queue,
                }
                proc = self.check(data)
                self.assertEqual(proc.returncode, 1, proc.stdout)
                self.assertIn("QUEUE: FAIL", proc.stdout)
                self.assertIn(expected, proc.stdout)
                plan = self.plan(data)
                self.assertEqual(plan.returncode, 1)
                report = json.loads(self.plan(data, "--json").stdout)
                self.assertFalse(report["ok"])
                self.assertTrue(report["errors"])

    def test_missing_required_fields_fail(self):
        data = {
            "now": NOW,
            "running": [{"issue": "KAR-2", "lane": "standard", "severity": "S3",
                         "started_at": "2026-11-10T08:00:00Z"}],
            "queued": [{"id": "q-1", "issue": "KAR-3", "lane": "quick",
                        "enqueued_at": "2026-11-10T08:30:00Z"}],
        }
        proc = self.check(data)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("running[0].id", proc.stdout)
        self.assertIn("queued[0].severity", proc.stdout)

    def test_deterministic_tie_break_by_id(self):
        data = {
            "now": NOW,
            "running": [],
            "queued": [
                queued("q-b", "KAR-31", "quick", "S2", "2026-11-10T08:30:00Z"),
                queued("q-a", "KAR-32", "quick", "S2", "2026-11-10T08:30:00Z"),
            ],
        }
        proc, report = self.plan_json(data)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual([entry["id"] for entry in report["dispatch"]], ["q-a", "q-b"])

    def test_json_output_shape(self):
        data = {
            "now": NOW,
            "running": [running("run-1", "KAR-2", "standard", "S3")],
            "queued": [queued("q-1", "KAR-3", "quick", "S1")],
        }
        proc, report = self.plan_json(data)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        for key in ("ok", "now", "dispatch", "preemptions", "errors", "warnings"):
            self.assertIn(key, report)
        self.assertTrue(report["ok"])
        self.assertEqual(report["errors"], [])
        self.assertEqual([entry["rank"] for entry in report["dispatch"]], [1])
        entry = report["dispatch"][0]
        for key in ("rank", "id", "issue", "lane", "severity", "reason"):
            self.assertIn(key, entry)
        preemption = report["preemptions"][0]
        for key in ("running_id", "running_issue", "by_queued_id", "reason"):
            self.assertIn(key, preemption)

    def test_check_reports_ok(self):
        data = {
            "now": NOW,
            "running": [],
            "queued": [queued("q-1", "KAR-3", "quick", "S2")],
        }
        proc = self.check(data)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("QUEUE: OK", proc.stdout)

    def test_missing_queue_argument_exits_one(self):
        proc = run("plan")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("usage", proc.stderr.lower())


if __name__ == "__main__":
    unittest.main()
