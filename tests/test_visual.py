#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts/visual.py"
EXAMPLE_CONFIG = ROOT / "docs/examples/visual-config.json"
EXAMPLE_RESULTS = ROOT / "docs/examples/visual-results.json"

CAPTURE_COMMAND = r"""
import json, os
payload = {
    "diff_ratio": 0.0 if os.environ["KAR_VISUAL_SCREEN"] == "SC-02-settings" else 0.002,
    "baseline_sha": "a" * 16,
    "current_sha": "b" * 16,
    "artifact": "evidence/visual/%s-%s-%s.png" % (
        os.environ["KAR_VISUAL_SCREEN"],
        os.environ["KAR_VISUAL_BREAKPOINT"],
        os.environ["KAR_VISUAL_THEME"],
    ),
}
log_path = os.environ.get("KAR_TEST_LOG")
if log_path:
    record = {
        "screen": os.environ["KAR_VISUAL_SCREEN"],
        "breakpoint": os.environ["KAR_VISUAL_BREAKPOINT"],
        "theme": os.environ["KAR_VISUAL_THEME"],
        "url": os.environ["KAR_VISUAL_URL"],
        "width": os.environ["KAR_VISUAL_WIDTH"],
        "cwd": os.getcwd(),
    }
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")
print(json.dumps(payload))
"""


def run(*args, env=None):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        text=True,
        capture_output=True,
        env=env,
    )


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def example_results():
    return json.loads(EXAMPLE_RESULTS.read_text(encoding="utf-8"))


def capture_config(command, screens=None, breakpoints=None, themes=None):
    return {
        "version": 1,
        "tool": "playwright",
        "command": command,
        "breakpoints": breakpoints
        or [
            {"name": "mobile", "width": 375},
            {"name": "desktop", "width": 1440},
        ],
        "themes": themes or ["light"],
        "thresholds": {"max_diff_ratio": 0.005, "critical_max_diff_ratio": 0.0},
        "screens": screens
        or [
            {"id": "SC-01-home", "url": "/"},
            {"id": "SC-02-settings", "url": "/settings", "critical": True},
        ],
    }


class VisualTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def write_results(self, data, name="results.json"):
        return write_json(self.root / name, data)


class InitTest(VisualTestCase):
    def test_init_writes_template_and_refuses_overwrite_without_force(self):
        path = self.root / "visual.json"
        proc = run("init", "--out", str(path))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        config = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(config["version"], 1)
        self.assertEqual(config["tool"], "playwright")
        self.assertEqual(
            [item["name"] for item in config["breakpoints"]],
            ["mobile", "tablet", "desktop"],
        )
        self.assertEqual(config["themes"], ["light"])
        self.assertEqual(config["thresholds"]["max_diff_ratio"], 0.005)
        self.assertEqual(config["screens"][0]["id"], "SC-01-home")
        self.assertTrue(config["command"])

        proc = run("init", "--out", str(path))
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("--force", proc.stdout + proc.stderr)

        proc = run("init", "--out", str(path), "--force", "--json")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["created"])


class CheckTest(VisualTestCase):
    def check(self, results=None, config=None, as_json=False):
        cfg = EXAMPLE_CONFIG
        if config is not None:
            cfg = write_json(self.root / "visual.json", config)
        res = EXAMPLE_RESULTS
        if results is not None:
            res = self.write_results(results)
        args = ["check", "--config", str(cfg), "--results", str(res)]
        if as_json:
            args.append("--json")
        return run(*args)

    def test_example_config_and_results_pass(self):
        proc = self.check()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("VISUAL: OK", proc.stdout)
        self.assertIn("8/8", proc.stdout)

    def test_json_report_parses(self):
        proc = self.check(as_json=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        for key in ("ok", "tool", "coverage", "failures", "warnings", "errors"):
            self.assertIn(key, payload)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["tool"], "playwright")
        self.assertEqual(payload["coverage"]["expected"], 8)
        self.assertEqual(payload["coverage"]["covered"], 8)
        self.assertEqual(payload["errors"], [])
        self.assertEqual(payload["failures"], [])

    def test_missing_combination_fails(self):
        data = example_results()
        data["screens"] = [
            entry
            for entry in data["screens"]
            if (entry["screen"], entry["breakpoint"], entry["theme"])
            != ("SC-01-login", "mobile", "light")
        ]
        proc = self.check(data, as_json=True)
        self.assertNotEqual(proc.returncode, 0)
        payload = json.loads(proc.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["coverage"]["covered"], 7)
        self.assertTrue(
            any(
                "missing combination SC-01-login/mobile/light" in error
                for error in payload["errors"]
            )
        )

    def test_duplicate_combination_fails(self):
        data = example_results()
        data["screens"].append(dict(data["screens"][0]))
        proc = self.check(data, as_json=True)
        self.assertNotEqual(proc.returncode, 0)
        payload = json.loads(proc.stdout)
        self.assertFalse(payload["ok"])
        self.assertTrue(
            any("duplicate combination SC-01-login/mobile/light" in error for error in payload["errors"])
        )

    def test_critical_screen_over_threshold_fails(self):
        data = example_results()
        entry = next(
            item
            for item in data["screens"]
            if (item["screen"], item["breakpoint"], item["theme"])
            == ("SC-01-login", "mobile", "light")
        )
        entry["diff_ratio"] = 0.003
        entry["artifact"] = "evidence/visual/SC-01-login-mobile-light.png"
        proc = self.check(data, as_json=True)
        self.assertNotEqual(proc.returncode, 0)
        payload = json.loads(proc.stdout)
        self.assertFalse(payload["ok"])
        self.assertTrue(payload["failures"])
        message = "\n".join(payload["failures"])
        self.assertIn("SC-01-login/mobile/light", message)
        self.assertIn("0.003", message)
        self.assertIn("0.0", message)

    def test_non_critical_screen_within_threshold_passes(self):
        data = example_results()
        entry = next(
            item
            for item in data["screens"]
            if (item["screen"], item["breakpoint"], item["theme"])
            == ("SC-02-home", "mobile", "light")
        )
        entry["diff_ratio"] = 0.004
        proc = self.check(data)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("VISUAL: OK", proc.stdout)

    def test_critical_screens_list_marks_a_screen_critical(self):
        config = json.loads(EXAMPLE_CONFIG.read_text(encoding="utf-8"))
        config["screens"][0].pop("critical")
        self.assertEqual(config["critical_screens"], ["SC-01-login"])
        data = example_results()
        entry = data["screens"][0]
        entry["diff_ratio"] = 0.002
        proc = self.check(data, config=config, as_json=True)
        self.assertNotEqual(proc.returncode, 0)
        payload = json.loads(proc.stdout)
        self.assertTrue(
            any("critical threshold 0.0" in failure for failure in payload["failures"])
        )

    def test_tool_unavailable_fails_as_blocked(self):
        data = example_results()
        data["tool_available"] = False
        proc = self.check(data)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("工具不可用，不能判定通过（BLOCKED）", proc.stdout)

    def test_wrong_tool_fails(self):
        data = example_results()
        data["tool"] = "puppeteer"
        proc = self.check(data, as_json=True)
        self.assertNotEqual(proc.returncode, 0)
        payload = json.loads(proc.stdout)
        self.assertTrue(any("does not match config tool" in error for error in payload["errors"]))

    def test_invalid_timestamp_fails(self):
        data = example_results()
        data["generated_at"] = "2026-11-05 08:00:00"
        proc = self.check(data, as_json=True)
        self.assertNotEqual(proc.returncode, 0)
        payload = json.loads(proc.stdout)
        self.assertTrue(any("generated_at" in error for error in payload["errors"]))

    def test_bad_sha_and_diff_ratio_fail(self):
        for field, value in (
            ("baseline_sha", ""),
            ("current_sha", ""),
            ("diff_ratio", 1.25),
        ):
            with self.subTest(field=field):
                data = example_results()
                data["screens"][0][field] = value
                proc = self.check(data, as_json=True)
                self.assertNotEqual(proc.returncode, 0)
                payload = json.loads(proc.stdout)
                self.assertTrue(
                    any(field in error for error in payload["errors"]),
                    payload["errors"],
                )

    def test_unknown_screen_breakpoint_or_theme_fails(self):
        data = example_results()
        data["screens"][0]["breakpoint"] = "watch"
        proc = self.check(data, as_json=True)
        self.assertNotEqual(proc.returncode, 0)
        payload = json.loads(proc.stdout)
        self.assertTrue(any("unknown breakpoint" in error for error in payload["errors"]))

    def test_positive_diff_without_artifact_warns_but_passes(self):
        data = example_results()
        entry = next(
            item
            for item in data["screens"]
            if (item["screen"], item["breakpoint"], item["theme"])
            == ("SC-02-home", "mobile", "light")
        )
        entry["artifact"] = ""
        proc = self.check(data, as_json=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["ok"])
        self.assertTrue(any("artifact is empty" in warning for warning in payload["warnings"]))

    def test_invalid_config_is_rejected(self):
        config = json.loads(EXAMPLE_CONFIG.read_text(encoding="utf-8"))
        config["thresholds"]["critical_max_diff_ratio"] = 0.5
        config["breakpoints"].append({"name": "mobile", "width": 0})
        config["themes"].append("light")
        config["critical_screens"].append("SC-99-missing")
        proc = self.check(config=config, as_json=True)
        self.assertNotEqual(proc.returncode, 0)
        payload = json.loads(proc.stdout)
        errors = "\n".join(payload["errors"])
        self.assertIn("critical_max_diff_ratio", errors)
        self.assertIn("duplicate breakpoint name", errors)
        self.assertIn("duplicate theme", errors)
        self.assertIn("unknown screen 'SC-99-missing'", errors)


class CaptureTest(VisualTestCase):
    def capture(self, config, out=None, cwd=None, timeout=None, as_json=True, env=None):
        cfg = write_json(self.root / "visual.json", config)
        out = out or (self.root / "results.json")
        args = ["capture", "--config", str(cfg), "--out", str(out)]
        if cwd is not None:
            args += ["--cwd", str(cwd)]
        if timeout is not None:
            args += ["--timeout", str(timeout)]
        if as_json:
            args.append("--json")
        return run(*args, env=env), cfg, out

    def test_capture_runs_every_combination_and_passes_check(self):
        log = self.root / "calls.jsonl"
        cwd = self.root / "work"
        cwd.mkdir()
        env = os.environ.copy()
        env["KAR_TEST_LOG"] = str(log)
        config = capture_config([sys.executable, "-c", CAPTURE_COMMAND])

        proc, cfg, out = self.capture(config, cwd=cwd, env=env)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        data = json.loads(out.read_text(encoding="utf-8"))
        self.assertTrue(data["tool_available"])
        self.assertEqual(data["tool"], "playwright")
        self.assertEqual(len(data["screens"]), 4)
        self.assertRegex(data["generated_at"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

        calls = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(calls), 4)
        by_combo = {
            (call["screen"], call["breakpoint"], call["theme"]): call for call in calls
        }
        record = by_combo[("SC-01-home", "mobile", "light")]
        self.assertEqual(record["url"], "/")
        self.assertEqual(record["width"], "375")
        self.assertEqual(Path(record["cwd"]).resolve(), cwd.resolve())
        settings = by_combo[("SC-02-settings", "desktop", "light")]
        self.assertEqual(settings["url"], "/settings")
        self.assertEqual(settings["width"], "1440")

        check = run("check", "--config", str(cfg), "--results", str(out))
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
        self.assertIn("VISUAL: OK", check.stdout)
        self.assertIn("4/4", check.stdout)

    def test_capture_json_summary_parses(self):
        config = capture_config([sys.executable, "-c", CAPTURE_COMMAND])
        proc, _, out = self.capture(config)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["captured"], 4)
        self.assertEqual(payload["expected"], 4)
        self.assertEqual(payload["coverage"]["covered"], 4)
        self.assertTrue(out.exists())

    def test_capture_failing_command_writes_blocked_results(self):
        config = capture_config(
            [sys.executable, "-c", "import sys; sys.stderr.write('boom'); sys.exit(3)"],
            screens=[{"id": "SC-01-home", "url": "/"}],
            breakpoints=[{"name": "mobile", "width": 375}],
            themes=["light"],
        )
        proc, _, out = self.capture(config)
        self.assertEqual(proc.returncode, 1)
        data = json.loads(out.read_text(encoding="utf-8"))
        self.assertFalse(data["tool_available"])
        self.assertEqual(data["screens"], [])
        self.assertTrue(any("status 3" in error for error in data["errors"]))
        payload = json.loads(proc.stdout)
        self.assertFalse(payload["ok"])
        self.assertTrue(any("工具不可用" in error for error in payload["errors"]))

    def test_capture_unparseable_stdout_is_blocked(self):
        config = capture_config(
            [sys.executable, "-c", "print('not a json object')"],
            screens=[{"id": "SC-01-home", "url": "/"}],
            breakpoints=[{"name": "mobile", "width": 375}],
            themes=["light"],
        )
        proc, _, out = self.capture(config)
        self.assertEqual(proc.returncode, 1)
        data = json.loads(out.read_text(encoding="utf-8"))
        self.assertFalse(data["tool_available"])
        self.assertTrue(any("JSON" in error for error in data["errors"]))

    def test_capture_requires_current_sha(self):
        script = (
            "import json; print(json.dumps("
            "{'diff_ratio': 0.0, 'baseline_sha': 'a' * 16}))"
        )
        config = capture_config(
            [sys.executable, "-c", script],
            screens=[{"id": "SC-01-home", "url": "/"}],
            breakpoints=[{"name": "mobile", "width": 375}],
            themes=["light"],
        )
        proc, _, out = self.capture(config)
        self.assertEqual(proc.returncode, 1)
        data = json.loads(out.read_text(encoding="utf-8"))
        self.assertFalse(data["tool_available"])
        self.assertTrue(any("current_sha" in error for error in data["errors"]))

    def test_capture_timeout_is_blocked(self):
        config = capture_config(
            [sys.executable, "-c", "import time; time.sleep(10)"],
            screens=[{"id": "SC-01-home", "url": "/"}],
            breakpoints=[{"name": "mobile", "width": 375}],
            themes=["light"],
        )
        proc, _, out = self.capture(config, timeout=0.4)
        self.assertEqual(proc.returncode, 1)
        data = json.loads(out.read_text(encoding="utf-8"))
        self.assertFalse(data["tool_available"])
        self.assertTrue(any("timed out" in error for error in data["errors"]))


if __name__ == "__main__":
    unittest.main()
