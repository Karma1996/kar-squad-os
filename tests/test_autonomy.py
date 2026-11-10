#!/usr/bin/env python3
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts/autonomy.py"
sys.path.insert(0, str(ROOT / "scripts"))
from policy import validate_autonomy  # noqa: E402

H1_CHECKS = [
    {"id": "scope", "result": "pass", "evidence": "需求分析文档 v1.0 §2"},
    {"id": "prototype", "result": "n/a", "evidence": "无界面变更", "note": "纯工具改动"},
    {"id": "evidence", "result": "pass", "evidence": "issue 评论与 PR 链接"},
]


def autonomy_block(**overrides):
    block = {
        "project_opt_in": {
            "by": "owner-1",
            "at": "2026-11-01T08:00:00Z",
            "scope": "repo:storefront",
        },
        "reversible": True,
        "external_contract": False,
        "window_hours": 24,
        "wait_started_at": "2026-11-01T09:00:00Z",
        "notification": {
            "at": "2026-11-02T09:00:00Z",
            "actor": "owner-1",
            "channel": "issue comment",
        },
        "assumption": {
            "statement": "按现有测试命令与文档目录执行，不改接口。",
            "owner": "owner-1",
            "recorded_at": "2026-11-02T09:05:00Z",
        },
        "state": "assumed",
        "assumed_at": "2026-11-02T09:00:00Z",
    }
    block.update(overrides)
    return block


def base_manifest(**overrides):
    manifest = {
        "version": 2,
        "change_set_id": "KAR-7",
        "issue": "KAR-7",
        "slug": "low-risk-tooling",
        "risk": "R1",
        "lane": "standard",
        "decision_owner": "owner-1",
        "gates": {
            "h1": {
                "status": "assumed",
                "requested_at": "2026-11-01T09:00:00Z",
                "assumed_at": "2026-11-02T09:00:00Z",
                "approver_type": "assumption",
                "rationale": "低风险、可逆、无外部契约，静默 24h 后按假设推进。",
                "conditions": [],
                "checks": copy.deepcopy(H1_CHECKS),
            },
            "h2": {
                "status": "approved",
                "approved_at": "2026-11-03T10:00:00Z",
                "approver_type": "human",
                "approved_by": "owner-1",
                "rationale": "设计已确认。",
                "conditions": [],
            },
            "h3": {
                "status": "approved",
                "approved_at": "2026-11-04T10:00:00Z",
                "approver_type": "human",
                "approved_by": "owner-1",
                "rationale": "验收与合并已确认。",
                "conditions": [],
            },
        },
        "autonomy": autonomy_block(),
    }
    manifest.update(overrides)
    return manifest


def check(manifest, strict=True):
    errors: list[str] = []
    warnings: list[str] = []
    validate_autonomy(manifest, strict, errors, warnings)
    return errors, warnings


class AutonomyValidationTest(unittest.TestCase):
    def test_valid_assumed_block_passes(self):
        errors, warnings = check(base_manifest())
        self.assertEqual(errors, [], errors)
        self.assertEqual(warnings, [])

    def test_non_low_risk_is_rejected(self):
        errors, _ = check(base_manifest(risk="R2"))
        self.assertTrue(any("only R0/R1" in e for e in errors), errors)

    def test_program_child_is_rejected(self):
        errors, _ = check(base_manifest(program_child=True))
        self.assertTrue(any("Program children" in e for e in errors), errors)

    def test_irreversible_is_rejected(self):
        errors, _ = check(base_manifest(autonomy=autonomy_block(reversible=False)))
        self.assertTrue(any("reversible" in e for e in errors), errors)

    def test_external_contract_is_rejected(self):
        errors, _ = check(base_manifest(autonomy=autonomy_block(external_contract=True)))
        self.assertTrue(any("external_contract" in e for e in errors), errors)

    def test_short_window_is_rejected(self):
        errors, _ = check(base_manifest(autonomy=autonomy_block(window_hours=12)))
        self.assertTrue(any("window_hours" in e for e in errors), errors)

    def test_missing_human_opt_in_is_rejected(self):
        block = autonomy_block()
        block["project_opt_in"] = {"at": "2026-11-01T08:00:00Z", "scope": "repo:x"}
        errors, _ = check(base_manifest(autonomy=block))
        self.assertTrue(any("project_opt_in.by" in e for e in errors), errors)

    def test_assumption_before_24h_is_rejected(self):
        block = autonomy_block(assumed_at="2026-11-02T08:00:00Z")
        manifest = base_manifest(autonomy=block)
        manifest["gates"]["h1"]["assumed_at"] = "2026-11-02T08:00:00Z"
        errors, _ = check(manifest)
        self.assertTrue(any("24h window has not elapsed" in e for e in errors), errors)

    def test_reminder_must_not_precede_window(self):
        block = autonomy_block()
        block["notification"]["at"] = "2026-11-02T08:00:00Z"
        errors, _ = check(base_manifest(autonomy=block))
        self.assertTrue(any("may not precede the 24h window" in e for e in errors), errors)

    def test_missing_assumption_statement_is_rejected(self):
        block = autonomy_block()
        block["assumption"] = {"owner": "owner-1", "recorded_at": "2026-11-02T09:05:00Z"}
        errors, _ = check(base_manifest(autonomy=block))
        self.assertTrue(any("assumption.statement" in e for e in errors), errors)

    def test_assumed_gate_without_autonomy_block_is_rejected(self):
        manifest = base_manifest()
        manifest.pop("autonomy")
        errors, _ = check(manifest)
        self.assertTrue(any("required when gates.h1.status is assumed" in e for e in errors), errors)

    def test_overridden_fails_at_h3_but_only_warns_in_draft(self):
        block = autonomy_block(
            state="overridden",
            override={
                "by": "owner-1",
                "at": "2026-11-02T10:00:00Z",
                "decision": "rejected",
                "reason": "假设不成立，需要人类确认范围。",
            },
        )
        manifest = base_manifest(autonomy=block)
        manifest["gates"]["h1"]["status"] = "pending"
        errors, _ = check(manifest, strict=True)
        self.assertTrue(any("human rejected the assumption" in e for e in errors), errors)
        errors, warnings = check(manifest, strict=False)
        self.assertEqual(errors, [], errors)
        self.assertTrue(any("human rejected the assumption" in w for w in warnings), warnings)

    def test_human_gate_restored_requires_human_h1_approval(self):
        block = autonomy_block(
            state="approved",
            override={
                "by": "owner-1",
                "at": "2026-11-02T10:00:00Z",
                "decision": "human_gate_restored",
                "reason": "恢复 H1，由人类重新确认。",
            },
        )
        manifest = base_manifest(autonomy=block)
        manifest["gates"]["h1"] = {
            "status": "approved",
            "approved_at": "2026-11-02T11:00:00Z",
            "approver_type": "human",
            "approved_by": "owner-1",
            "rationale": "人类重新确认需求。",
            "conditions": [],
            "checks": copy.deepcopy(H1_CHECKS),
        }
        errors, _ = check(manifest)
        self.assertEqual(errors, [], errors)

    def test_human_approval_before_assumption_is_rejected(self):
        block = autonomy_block(state="approved")
        manifest = base_manifest(autonomy=block)
        manifest["gates"]["h1"] = {
            "status": "approved",
            "approved_at": "2026-11-02T08:00:00Z",
            "approver_type": "human",
            "approved_by": "owner-1",
            "rationale": "提前批准。",
            "conditions": [],
            "checks": copy.deepcopy(H1_CHECKS),
        }
        errors, _ = check(manifest)
        self.assertTrue(any("normal early H1 approval" in e for e in errors), errors)


class AutonomyCliTest(unittest.TestCase):
    def run_cli(self, manifest, *args):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "delivery-manifest.json"
            path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(SCRIPT), *args, "--manifest", str(path)],
                text=True,
                capture_output=True,
            )

    def test_check_passes_and_reports_deadline(self):
        proc = self.run_cli(base_manifest(), "check")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("AUTONOMY: OK", proc.stdout)
        self.assertIn("H3 still requires a human approval", proc.stdout)
        proc = self.run_cli(base_manifest(), "deadline", "--json")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["deadline"], "2026-11-02T09:00:00Z")
        self.assertTrue(payload["eligible"])

    def test_check_fails_for_ineligible_risk(self):
        proc = self.run_cli(base_manifest(risk="R2"), "check")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("AUTONOMY: FAIL", proc.stdout)

    def test_json_output_is_machine_readable(self):
        proc = self.run_cli(base_manifest(risk="R2"), "check", "--json")
        payload = json.loads(proc.stdout)
        self.assertFalse(payload["ok"])
        self.assertTrue(payload["errors"])

    def test_deadline_without_block_fails(self):
        manifest = base_manifest()
        manifest.pop("autonomy")
        proc = self.run_cli(manifest, "deadline")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("N/A", proc.stdout)


if __name__ == "__main__":
    unittest.main()
