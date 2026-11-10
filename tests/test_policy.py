#!/usr/bin/env python3
import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts/policy.py"
sys.path.insert(0, str(ROOT / "scripts"))
from policy import validate_policy  # noqa: E402


def artifact(kind, version="1.0"):
    return {"kind": kind, "ref": f"docs/{kind}.html", "version": version}


def base_manifest(risk="R2"):
    return {
        "version": 2,
        "change_set_id": "KAR-1",
        "issue": "KAR-1",
        "slug": "policy-check",
        "risk": risk,
        "lane": "standard",
        "docs": {
            "requirements": {"version": "1.0"},
            "design": {"version": "2.0"},
            "test_design": {"version": "1.0"},
        },
        "gates": {
            "h1": {"requested_at": "2026-11-01T01:00:00Z", "approved_at": "2026-11-01T02:00:00Z"},
            "h2": {"requested_at": "2026-11-01T04:00:00Z", "approved_at": "2026-11-01T05:00:00Z"},
            "h3": {"requested_at": "2026-11-02T01:00:00Z", "approved_at": "2026-11-02T02:00:00Z"},
        },
        "artifacts": [artifact("requirements"), artifact("design"), artifact("test_design")],
        "checkpoints": {
            "h1_draft": {
                "published_at": "2026-11-01T00:40:00Z",
                "review_window_minutes": 10,
                "reviewers": ["owner-1"],
                "outcome": "unchanged",
                "steer_ids": [],
            },
            "h2_draft": {
                "published_at": "2026-11-01T03:40:00Z",
                "review_window_minutes": 10,
                "reviewers": ["owner-1"],
                "outcome": "unchanged",
                "steer_ids": [],
            },
        },
        "steers": [],
        "touchpoints": [
            {"kind": "intake", "at": "2026-11-01T00:30:00Z", "actor": "owner-1"},
            {"kind": "contract", "at": "2026-11-01T00:50:00Z", "actor": "owner-1"},
            {"kind": "gates", "gate": "h1", "at": "2026-11-01T01:00:00Z", "actor": "owner-1"},
            {"kind": "gates", "gate": "h2", "at": "2026-11-01T04:00:00Z", "actor": "owner-1"},
            {"kind": "gates", "gate": "h3", "at": "2026-11-02T01:00:00Z", "actor": "owner-1"},
        ],
    }


def security_overlay():
    return {
        "threat_model": {"path": "docs/threat-model.html", "version": "1.0", "sha": "a" * 64},
        "permission_matrix": {"path": "docs/permissions.html", "version": "1.0", "sha": "b" * 64},
        "secret_scan": {"tool": "gitleaks", "status": "passed", "findings": 0, "at": "2026-11-01T00:00:00Z"},
        "dependency_scan": {"tool": "osv-scanner", "status": "passed", "findings": 0, "at": "2026-11-01T00:00:00Z"},
        "rollback_drill": {"at": "2026-11-01T00:00:00Z", "result": "passed", "evidence": "evidence/drill.md"},
        "reviewer": {
            "id": "security-1",
            "role": "security",
            "independent": True,
            "verdict": "pass",
            "at": "2026-11-01T00:30:00Z",
            "scope": "authz, secrets, rollback",
        },
    }


def r3_manifest():
    data = base_manifest("R3")
    data["docs"]["prototype"] = {"version": "1.0", "mode": "B"}
    data["artifacts"] = [
        artifact("requirements"),
        artifact("prototype"),
        artifact("design"),
        artifact("test_design"),
        artifact("dev_notes"),
        artifact("qa_report"),
        artifact("security_overlay"),
    ]
    data["security_overlay"] = security_overlay()
    data["gates"]["h3"]["second_reviewer"] = {
        "reviewer": "security-1",
        "role": "security",
        "verdict": "pass",
        "at": "2026-11-01T00:30:00Z",
    }
    return data


def errors_for(manifest, profile="h3"):
    errors, warnings = validate_policy(manifest, profile)
    return errors, warnings


def run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], text=True, capture_output=True)


class ArtifactMatrixTest(unittest.TestCase):
    def test_example_manifest_passes(self):
        data = json.loads((ROOT / "docs/examples/delivery-manifest.json").read_text(encoding="utf-8"))
        errors, warnings = errors_for(data)
        self.assertEqual(errors, [], warnings)

    def test_r2_requires_exactly_three(self):
        errors, _ = errors_for(base_manifest())
        self.assertEqual(errors, [])
        data = copy.deepcopy(base_manifest())
        data["artifacts"].append(artifact("dev_notes"))
        self.assertTrue(any("at most 3" in e for e in errors_for(data)[0]))
        data = copy.deepcopy(base_manifest())
        data["artifacts"] = [artifact("requirements"), artifact("design")]
        self.assertTrue(any("at least 3" in e for e in errors_for(data)[0]))

    def test_r1_caps_at_three_and_allows_light_artifacts(self):
        data = base_manifest("R1")
        data["artifacts"] = [artifact("issue_record"), artifact("pr"), artifact("test_evidence")]
        self.assertEqual(errors_for(data)[0], [])
        data["artifacts"].append(artifact("dev_notes"))
        self.assertTrue(any("at most 3" in e for e in errors_for(data)[0]))

    def test_r3_requires_full_set(self):
        data = r3_manifest()
        self.assertEqual(errors_for(data)[0], [])
        data = copy.deepcopy(data)
        data["artifacts"] = [a for a in data["artifacts"] if a["kind"] != "dev_notes"]
        self.assertTrue(any("dev_notes" in e and "requires kinds" in e for e in errors_for(data)[0]))

    def test_r3_requires_prototype_when_bound(self):
        data = r3_manifest()
        data["artifacts"] = [a for a in data["artifacts"] if a["kind"] != "prototype"]
        self.assertTrue(any("prototype" in e and "requires kinds" in e for e in errors_for(data)[0]))

    def test_program_child_budget(self):
        data = base_manifest("R3")
        data["program_child"] = True
        data["artifacts"] = [artifact("dev_notes"), artifact("design")]
        self.assertEqual(errors_for(data)[0], [])
        for key in ("gates", "checkpoints", "steers", "touchpoints", "security_overlay"):
            data.pop(key, None)
        self.assertEqual(errors_for(data)[0], [])
        data["artifacts"].append(artifact("requirements"))
        self.assertTrue(any("program child" in e and "at most 2" in e for e in errors_for(data)[0]))
        data["artifacts"] = [artifact("design")]
        self.assertTrue(any("dev_notes" in e for e in errors_for(data)[0]))

    def test_duplicate_and_unknown_kind_fail(self):
        data = base_manifest()
        data["artifacts"] = [artifact("requirements"), artifact("requirements"), artifact("design")]
        self.assertTrue(any("duplicate" in e for e in errors_for(data)[0]))
        data = base_manifest()
        data["artifacts"] = [artifact("requirements"), artifact("design"), artifact("mystery")]
        self.assertTrue(any("kind" in e for e in errors_for(data)[0]))

    def test_missing_ref_fails(self):
        data = base_manifest()
        data["artifacts"][0]["ref"] = ""
        self.assertTrue(any("ref" in e for e in errors_for(data)[0]))


class SecurityOverlayTest(unittest.TestCase):
    def test_r3_requires_overlay(self):
        data = r3_manifest()
        del data["security_overlay"]
        self.assertTrue(any("security_overlay" in e for e in errors_for(data)[0]))

    def test_r2_does_not_require_overlay(self):
        self.assertEqual(errors_for(base_manifest("R2"))[0], [])

    def test_scans_must_pass_without_findings(self):
        data = r3_manifest()
        data["security_overlay"]["secret_scan"]["status"] = "failed"
        data["security_overlay"]["dependency_scan"]["findings"] = 2
        errs = errors_for(data)[0]
        self.assertTrue(any("secret_scan" in e and "did not pass" in e for e in errs))
        self.assertTrue(any("dependency_scan.findings" in e for e in errs))

    def test_rollback_drill_must_pass(self):
        data = r3_manifest()
        data["security_overlay"]["rollback_drill"]["result"] = "failed"
        self.assertTrue(any("rollback drill must pass" in e for e in errors_for(data)[0]))

    def test_reviewer_must_be_independent_and_match_second_reviewer(self):
        data = r3_manifest()
        data["security_overlay"]["reviewer"]["independent"] = False
        self.assertTrue(any("independent" in e for e in errors_for(data)[0]))
        data = r3_manifest()
        data["gates"]["h3"]["second_reviewer"]["reviewer"] = "someone-else"
        self.assertTrue(any("must match" in e for e in errors_for(data)[0]))
        data = r3_manifest()
        data["gates"]["h3"]["second_reviewer"]["role"] = "domain"
        self.assertTrue(any("second_reviewer.role" in e for e in errors_for(data)[0]))


class CheckpointSteerTest(unittest.TestCase):
    def test_draft_must_be_published_ten_minutes_early(self):
        data = base_manifest()
        data["checkpoints"]["h1_draft"]["published_at"] = "2026-11-01T00:55:00Z"
        self.assertTrue(any("10 minutes" in e for e in errors_for(data)[0]))

    def test_missing_checkpoint_fails_h3(self):
        data = base_manifest()
        del data["checkpoints"]["h2_draft"]
        self.assertTrue(any("h2_draft" in e for e in errors_for(data)[0]))

    def test_short_review_window_fails(self):
        data = base_manifest()
        data["checkpoints"]["h1_draft"]["review_window_minutes"] = 5
        self.assertTrue(any("review_window_minutes" in e for e in errors_for(data)[0]))

    def test_steered_checkpoint_needs_ledger_entry(self):
        data = base_manifest()
        data["checkpoints"]["h2_draft"]["outcome"] = "steered"
        self.assertTrue(any("steer_ids" in e for e in errors_for(data)[0]))
        data["checkpoints"]["h2_draft"]["steer_ids"] = ["ST-1"]
        data["steers"] = [{
            "id": "ST-1",
            "at": "2026-11-01T03:50:00Z",
            "gate": "h2",
            "from": "owner-1",
            "summary": "把重试改成 3 次。",
            "applied": True,
            "version_after": "2.0",
            "recorded_by": "KAR-01-Lead",
        }]
        self.assertEqual(errors_for(data)[0], [])

    def test_steer_version_must_match_doc(self):
        data = base_manifest()
        data["checkpoints"]["h2_draft"].update({"outcome": "steered", "steer_ids": ["ST-1"]})
        data["steers"] = [{
            "id": "ST-1",
            "at": "2026-11-01T03:50:00Z",
            "gate": "h2",
            "from": "owner-1",
            "summary": "改范围。",
            "applied": True,
            "version_after": "1.9",
            "recorded_by": "KAR-01-Lead",
        }]
        self.assertTrue(any("version_after" in e for e in errors_for(data)[0]))

    def test_orphan_steer_fails(self):
        data = base_manifest()
        data["steers"] = [{
            "id": "ST-9",
            "at": "2026-11-01T01:30:00Z",
            "gate": "h1",
            "from": "owner-1",
            "summary": "增加导出范围。",
            "applied": True,
            "version_after": "1.0",
            "recorded_by": "KAR-01-Lead",
        }]
        self.assertTrue(any("not linked" in e for e in errors_for(data)[0]))

    def test_deferred_steer_needs_reason_and_approver(self):
        data = base_manifest()
        data["checkpoints"]["h2_draft"].update({"outcome": "steered", "steer_ids": ["ST-1"]})
        data["steers"] = [{
            "id": "ST-1",
            "at": "2026-11-01T03:50:00Z",
            "gate": "h2",
            "from": "owner-1",
            "summary": "下个迭代再改。",
            "applied": False,
            "recorded_by": "KAR-01-Lead",
        }]
        errs = errors_for(data)[0]
        self.assertTrue(any("deferred_reason" in e for e in errs))
        self.assertTrue(any("deferred_approved_by" in e for e in errs))


class TouchpointBudgetTest(unittest.TestCase):
    def test_unknown_kind_fails(self):
        data = base_manifest()
        data["touchpoints"].append({"kind": "chat", "at": "2026-11-01T00:00:00Z", "actor": "owner-1"})
        self.assertTrue(any("touchpoints" in e and "kind" in e for e in errors_for(data)[0]))

    def test_intake_budget_is_one(self):
        data = base_manifest()
        data["touchpoints"].append({"kind": "intake", "at": "2026-11-01T00:31:00Z", "actor": "owner-1"})
        self.assertTrue(any("intake used 2" in e for e in errors_for(data)[0]))

    def test_duplicate_gate_fails(self):
        data = base_manifest()
        data["touchpoints"].append({"kind": "gates", "gate": "h1", "at": "2026-11-01T01:01:00Z", "actor": "owner-1"})
        self.assertTrue(any("duplicate gate" in e for e in errors_for(data)[0]))

    def test_missing_gate_record_fails(self):
        data = base_manifest()
        data["touchpoints"] = [t for t in data["touchpoints"] if t.get("gate") != "h3"]
        self.assertTrue(any("missing gate touchpoint" in e for e in errors_for(data)[0]))

    def test_exception_needs_reason(self):
        data = base_manifest()
        data["touchpoints"].append({"kind": "exception", "at": "2026-11-01T06:00:00Z", "actor": "owner-1"})
        self.assertTrue(any("reason" in e for e in errors_for(data)[0]))
        data["touchpoints"][-1]["reason"] = "CI 环境故障，需人类确认是否重跑。"
        self.assertEqual(errors_for(data)[0], [])

    def test_quick_lane_uses_single_quick_gate(self):
        data = base_manifest("R1")
        data["lane"] = "quick"
        data["artifacts"] = [artifact("issue_record"), artifact("pr")]
        data["touchpoints"] = [
            {"kind": "intake", "at": "2026-11-01T00:30:00Z", "actor": "owner-1"},
            {"kind": "gates", "gate": "quick", "at": "2026-11-01T01:00:00Z", "actor": "owner-1"},
        ]
        self.assertEqual(errors_for(data)[0], [])
        data["touchpoints"].append({"kind": "gates", "gate": "h1", "at": "2026-11-01T02:00:00Z", "actor": "owner-1"})
        self.assertTrue(any("quick lane" in e for e in errors_for(data)[0]))


class DraftProfileTest(unittest.TestCase):
    def test_draft_profile_is_advisory(self):
        data = {"version": 2, "change_set_id": "KAR-1", "issue": "KAR-1", "slug": "x", "risk": "R3"}
        errors, warnings = errors_for(data, "draft")
        self.assertEqual(errors, [])
        self.assertTrue(warnings)


class PolicyCliTest(unittest.TestCase):
    def test_cli_example_ok(self):
        proc = run("check", "--manifest", str(ROOT / "docs/examples/delivery-manifest.json"), "--profile", "h3")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("POLICY: OK", proc.stdout)

    def test_cli_json_failure(self):
        proc = run("check", "--manifest", str(ROOT / "docs/examples/delivery-manifest.json"),
                   "--profile", "h3", "--json")
        self.assertEqual(proc.returncode, 0)
        data = json.loads(proc.stdout)
        self.assertTrue(data["ok"])

    def test_matrix_prints_tiers(self):
        proc = run("matrix")
        self.assertEqual(proc.returncode, 0)
        for needle in ("R0 / R1", "R2", "R3", "Program 子级"):
            self.assertIn(needle, proc.stdout)


if __name__ == "__main__":
    unittest.main()


class AutonomyPolicyTest(unittest.TestCase):
    def low_risk_manifest(self):
        data = base_manifest("R1")
        data["artifacts"] = [artifact("issue_record"), artifact("pr"), artifact("test_evidence")]
        data["gates"]["h1"] = {
            "status": "assumed",
            "requested_at": "2026-11-01T01:00:00Z",
            "assumed_at": "2026-11-02T01:00:00Z",
            "approver_type": "assumption",
            "rationale": "R1 可逆改动，静默 24h 后按假设推进。",
            "conditions": [],
        }
        data["autonomy"] = {
            "project_opt_in": {"by": "owner-1", "at": "2026-10-31T00:00:00Z", "scope": "repo:x"},
            "reversible": True,
            "external_contract": False,
            "window_hours": 24,
            "wait_started_at": "2026-11-01T01:00:00Z",
            "notification": {"at": "2026-11-02T01:00:00Z", "actor": "owner-1", "channel": "issue comment"},
            "assumption": {"statement": "按现有测试与目录推进。", "owner": "owner-1", "recorded_at": "2026-11-02T01:05:00Z"},
            "state": "assumed",
            "assumed_at": "2026-11-02T01:00:00Z",
        }
        return data

    def test_valid_assumed_manifest_passes(self):
        errors, warnings = errors_for(self.low_risk_manifest())
        self.assertEqual(errors, [], errors + warnings)

    def test_assumed_gate_without_block_fails(self):
        data = self.low_risk_manifest()
        del data["autonomy"]
        self.assertTrue(any("autonomy" in e for e in errors_for(data)[0]))

    def test_overridden_assumption_fails_at_h3(self):
        data = self.low_risk_manifest()
        data["autonomy"]["state"] = "overridden"
        data["autonomy"]["override"] = {
            "by": "owner-1", "at": "2026-11-02T02:00:00Z",
            "decision": "rejected", "reason": "假设不成立。",
        }
        data["gates"]["h1"]["status"] = "pending"
        self.assertTrue(any("human rejected the assumption" in e for e in errors_for(data)[0]))

    def test_r2_cannot_use_autonomy(self):
        data = self.low_risk_manifest()
        data["risk"] = "R2"
        self.assertTrue(any("only R0/R1" in e for e in errors_for(data)[0]))


def visual_block():
    return {
        "config": {"path": "multica/project/visual.json", "version": "1.0", "sha": "c" * 64},
        "tool": "playwright",
        "breakpoints": ["mobile", "desktop"],
        "themes": ["light"],
        "thresholds": {"max_diff_ratio": 0.005, "critical_max_diff_ratio": 0.0},
        "results": [
            {"screen": "SC-01-login", "breakpoint": "mobile", "theme": "light", "diff_ratio": 0.0, "critical": True},
            {"screen": "SC-01-login", "breakpoint": "desktop", "theme": "light", "diff_ratio": 0.001},
        ],
        "passed": True,
        "at": "2026-11-01T00:00:00Z",
    }


class VisualRegressionPolicyTest(unittest.TestCase):
    def ui_manifest(self):
        data = base_manifest("R2")
        data["ui_affected"] = True
        data["visual_regression"] = visual_block()
        return data

    def test_valid_visual_summary_passes(self):
        errors, warnings = errors_for(self.ui_manifest())
        self.assertEqual(errors, [], errors + warnings)

    def test_ui_change_requires_visual_summary_at_h3(self):
        data = self.ui_manifest()
        del data["visual_regression"]
        self.assertTrue(any("visual_regression: required" in e for e in errors_for(data)[0]))

    def test_visual_failure_blocks_h3(self):
        data = self.ui_manifest()
        data["visual_regression"]["passed"] = False
        self.assertTrue(any("must pass at H3" in e for e in errors_for(data)[0]))

    def test_threshold_breach_is_reported(self):
        data = self.ui_manifest()
        data["visual_regression"]["results"][0]["diff_ratio"] = 0.01
        self.assertTrue(any("exceeds the critical threshold" in e for e in errors_for(data)[0]))

    def test_unknown_breakpoint_is_rejected(self):
        data = self.ui_manifest()
        data["visual_regression"]["results"][1]["breakpoint"] = "watch"
        self.assertTrue(any("unknown breakpoint" in e for e in errors_for(data)[0]))

    def test_non_ui_block_only_warns(self):
        data = self.ui_manifest()
        data["ui_affected"] = False
        errors, warnings = errors_for(data)
        self.assertEqual(errors, [], errors)
        self.assertTrue(any("only required when ui_affected" in w for w in warnings))
