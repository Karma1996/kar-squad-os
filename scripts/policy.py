#!/usr/bin/env python3
"""v4.3 governance policy checks for a KAR delivery manifest.

The four P1 controls introduced in v4.3 live here so they can be tested and
run on their own:

* artifact matrix    - how many formal deliverables each risk tier may spend
* security overlay   - R3 threat model, permission matrix, scans, rollback drill
* draft checkpoints  - H1/H2 drafts published at least 10 minutes before the gate
* steer ledger       - corrections made during draft review are recorded
* touchpoint budget  - the Lead may only touch humans at six contact points

Only the Python standard library is used. ``manifest.py check --profile h3``
calls :func:`validate_policy`, so a manifest cannot pass H3 while violating
these rules. Run ``policy.py check`` for a fast, file-free audit.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from kar_common import GATE_ORDER, load_manifest, parse_time

# --- artifact matrix -------------------------------------------------------

ARTIFACT_KINDS = frozenset({
    "requirements",
    "prototype",
    "design",
    "test_design",
    "dev_notes",
    "qa_report",
    "security_overlay",
    "issue_record",
    "pr",
    "test_evidence",
    "retro",
})

RISK_ARTIFACT_LIMITS = {
    "R0": (1, 3),
    "R1": (1, 3),
    "R2": (3, 3),
}

R2_REQUIRED = frozenset({"requirements", "design", "test_design"})
R3_REQUIRED = frozenset({
    "requirements",
    "design",
    "test_design",
    "dev_notes",
    "qa_report",
    "security_overlay",
})
PROGRAM_CHILD_LIMITS = (1, 2)
PROGRAM_CHILD_REQUIRED = frozenset({"dev_notes"})

# --- R3 security overlay ---------------------------------------------------

SCAN_STATUSES = ("passed", "failed")
ROLLBACK_RESULTS = ("passed", "failed")
SHA_RE = r"^[0-9a-f]{64}$"

# --- draft checkpoint / steer ---------------------------------------------

CHECKPOINT_MINUTES = 10
CHECKPOINT_GATES = ("h1", "h2")
STEER_GATES = ("h1", "h2")
CHECKPOINT_OUTCOMES = ("unchanged", "steered")
STEER_VERSION_DOC = {"h1": "requirements", "h2": "design"}

# --- lead touchpoint budget ------------------------------------------------

TOUCHPOINT_KINDS = ("intake", "contract", "gates", "integration", "merge", "exception")
TOUCHPOINT_CAPS = {
    "quick": {"intake": 1, "contract": 1, "gates": 1, "integration": 1, "merge": 1},
    "standard": {"intake": 1, "contract": 1, "gates": 3, "integration": 1, "merge": 1},
    "program": {"intake": 1, "contract": 1, "gates": 3, "integration": 1, "merge": 1},
}
LANES = ("quick", "standard", "program")
QUICK_GATE = "quick"


def _nonempty(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _timestamp(value) -> bool:
    return parse_time(value) is not None


def _is_count(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _artifact_budget(manifest: dict):
    """Return (min, max), required kinds and the label used in messages."""
    if manifest.get("program_child") is True:
        return PROGRAM_CHILD_LIMITS, PROGRAM_CHILD_REQUIRED, "program child"
    risk = str(manifest.get("risk") or "").upper()
    if risk not in ("R0", "R1", "R2", "R3"):
        return None, frozenset(), "unknown risk"
    if risk == "R3":
        docs = manifest.get("docs") or {}
        required = set(R3_REQUIRED)
        if isinstance(docs.get("prototype"), dict):
            required.add("prototype")
        return (len(required), None), frozenset(required), risk
    return RISK_ARTIFACT_LIMITS[risk], R2_REQUIRED if risk == "R2" else frozenset(), risk


def validate_artifacts(manifest: dict, strict: bool, errors: list, warnings: list) -> None:
    artifacts = manifest.get("artifacts")
    if artifacts is None:
        (errors if strict else warnings).append(
            "artifacts: required at H3 (formal deliverables for this risk tier)"
        )
        return
    if not isinstance(artifacts, list):
        errors.append("artifacts: expected a list")
        return
    budget, required, label = _artifact_budget(manifest)
    if budget is None:
        errors.append("artifacts: cannot check without a valid risk (R0-R3)")
        return
    low, high = budget
    seen: set[str] = set()
    for i, entry in enumerate(artifacts):
        where = f"artifacts[{i}]"
        if not isinstance(entry, dict):
            errors.append(f"{where}: must be an object")
            continue
        kind = entry.get("kind")
        if kind not in ARTIFACT_KINDS:
            errors.append(f"{where}.kind: expected one of {', '.join(sorted(ARTIFACT_KINDS))}")
        elif kind in seen:
            errors.append(f"{where}.kind: duplicate artifact kind {kind}")
        else:
            seen.add(kind)
        if not _nonempty(entry.get("ref")):
            errors.append(f"{where}.ref: required (path, PR or issue-comment reference)")
        if entry.get("version") is not None and not _nonempty(entry.get("version")):
            errors.append(f"{where}.version: must be a non-empty string when set")
    count = len(artifacts)
    if count < low:
        errors.append(f"artifacts: {label} requires at least {low} deliverable(s), got {count}")
    if high is not None and count > high:
        errors.append(f"artifacts: {label} allows at most {high} deliverable(s), got {count}")
    if strict:
        missing = sorted(required - seen)
        if missing:
            errors.append(f"artifacts: {label} requires kinds {', '.join(missing)}")


def _check_doc_entry(overlay: dict, key: str, errors: list, prefix: str = "security_overlay") -> None:
    entry = overlay.get(key)
    if not isinstance(entry, dict):
        errors.append(f"{prefix}.{key}: required object (path/version/sha)")
        return
    if not _nonempty(entry.get("path")):
        errors.append(f"{prefix}.{key}.path: required")
    if not _nonempty(entry.get("version")):
        errors.append(f"{prefix}.{key}.version: required")
    sha = entry.get("sha")
    if not _nonempty(sha) or not re.fullmatch(SHA_RE, str(sha)):
        errors.append(f"{prefix}.{key}.sha: expected 64-char lowercase hex")


def _check_scan(overlay: dict, key: str, strict: bool, errors: list, warnings: list) -> None:
    scan = overlay.get(key)
    prefix = f"security_overlay.{key}"
    if not isinstance(scan, dict):
        errors.append(f"{prefix}: required object (tool/status/findings/at)")
        return
    if not _nonempty(scan.get("tool")):
        errors.append(f"{prefix}.tool: required")
    status = scan.get("status")
    if status not in SCAN_STATUSES:
        errors.append(f"{prefix}.status: expected one of {', '.join(SCAN_STATUSES)}")
    if not _is_count(scan.get("findings")):
        errors.append(f"{prefix}.findings: non-negative integer required")
    if not _timestamp(scan.get("at")):
        errors.append(f"{prefix}.at: invalid timestamp")
    if strict:
        if status != "passed":
            errors.append(f"{prefix}: {key.replace('_', ' ')} did not pass at H3")
        findings = scan.get("findings")
        if _is_count(findings) and findings > 0:
            errors.append(f"{prefix}.findings: must be 0 at H3; unresolved findings block the gate")


def validate_security_overlay(manifest: dict, strict: bool, errors: list, warnings: list) -> None:
    risk = str(manifest.get("risk") or "").upper()
    overlay = manifest.get("security_overlay")
    if overlay is None:
        if strict and risk == "R3" and manifest.get("program_child") is not True:
            errors.append("security_overlay: required for R3 (threat model, permission matrix, scans, rollback drill, reviewer)")
        return
    if not isinstance(overlay, dict):
        errors.append("security_overlay: expected an object")
        return
    if risk != "R3":
        warnings.append("security_overlay: only required for R3; recorded anyway")
    for key in ("threat_model", "permission_matrix"):
        _check_doc_entry(overlay, key, errors)
    for key in ("secret_scan", "dependency_scan"):
        _check_scan(overlay, key, strict, errors, warnings)
    drill = overlay.get("rollback_drill")
    if not isinstance(drill, dict):
        errors.append("security_overlay.rollback_drill: required object (at/result/evidence)")
    else:
        if not _timestamp(drill.get("at")):
            errors.append("security_overlay.rollback_drill.at: invalid timestamp")
        if drill.get("result") not in ROLLBACK_RESULTS:
            errors.append("security_overlay.rollback_drill.result: expected passed or failed")
        elif strict and drill.get("result") != "passed":
            errors.append("security_overlay.rollback_drill: rollback drill must pass at H3")
        if not _nonempty(drill.get("evidence")):
            errors.append("security_overlay.rollback_drill.evidence: required")
    reviewer = overlay.get("reviewer")
    if not isinstance(reviewer, dict):
        errors.append("security_overlay.reviewer: required object (id/role/independent/verdict/at/scope)")
        return
    if not _nonempty(reviewer.get("id")):
        errors.append("security_overlay.reviewer.id: required")
    if reviewer.get("role") != "security":
        errors.append("security_overlay.reviewer.role: expected security (independent security reviewer)")
    if reviewer.get("independent") is not True:
        errors.append("security_overlay.reviewer.independent: must be true")
    if reviewer.get("verdict") != "pass":
        errors.append("security_overlay.reviewer.verdict: must be pass")
    if not _timestamp(reviewer.get("at")):
        errors.append("security_overlay.reviewer.at: invalid timestamp")
    if not _nonempty(reviewer.get("scope")):
        errors.append("security_overlay.reviewer.scope: required (what was reviewed)")
    reviewer_id = reviewer.get("id")
    for field in ("developer", "reviewer"):
        if _nonempty(manifest.get(field)) and manifest.get(field) == reviewer_id:
            errors.append(f"security_overlay.reviewer.id: must not be the change set {field}")
    gates = manifest.get("gates")
    second = (gates or {}).get("h3", {}).get("second_reviewer") if isinstance(gates, dict) else None
    if isinstance(second, dict):
        if second.get("role") != "security":
            errors.append("gates.h3.second_reviewer.role: must be security for R3")
        if second.get("reviewer") != reviewer_id:
            errors.append(
                "security_overlay.reviewer.id: must match gates.h3.second_reviewer.reviewer "
                "(one independent security reviewer signs both)"
            )


def validate_steers(manifest: dict, strict: bool, errors: list, warnings: list) -> dict[str, dict]:
    steers = manifest.get("steers")
    if steers is None:
        (errors if strict else warnings).append(
            "steers: required at H3 (decision ledger for draft corrections; [] when none)"
        )
        return {}
    if not isinstance(steers, list):
        errors.append("steers: expected a list")
        return {}
    gates = manifest.get("gates") or {}
    docs = manifest.get("docs") or {}
    by_id: dict[str, dict] = {}
    for i, steer in enumerate(steers):
        where = f"steers[{i}]"
        if not isinstance(steer, dict):
            errors.append(f"{where}: must be an object")
            continue
        sid = steer.get("id")
        if not _nonempty(sid):
            errors.append(f"{where}.id: required")
        elif sid in by_id:
            errors.append(f"{where}.id: duplicate steer id {sid}")
        else:
            by_id[sid] = steer
        gate = steer.get("gate")
        if gate not in STEER_GATES:
            errors.append(f"{where}.gate: expected h1 or h2")
        if not _nonempty(steer.get("from")):
            errors.append(f"{where}.from: required (the human who asked for the correction)")
        summary = steer.get("summary")
        if not _nonempty(summary):
            errors.append(f"{where}.summary: required (one line)")
        elif len(summary.strip()) > 280:
            errors.append(f"{where}.summary: keep to one line (<=280 chars)")
        if not _timestamp(steer.get("at")):
            errors.append(f"{where}.at: invalid timestamp")
        if not _nonempty(steer.get("recorded_by")):
            errors.append(f"{where}.recorded_by: required (Lead writes the ledger)")
        applied = steer.get("applied")
        if not isinstance(applied, bool):
            errors.append(f"{where}.applied: expected true or false")
        if applied is True:
            if not _nonempty(steer.get("version_after")):
                errors.append(f"{where}.version_after: required for an applied steer")
            doc_key = STEER_VERSION_DOC.get(gate) if isinstance(gate, str) else None
            expected = (docs.get(doc_key) or {}).get("version") if doc_key else None
            if expected and steer.get("version_after") != expected:
                errors.append(
                    f"{where}.version_after: must equal docs.{doc_key}.version ({expected}) after the steer"
                )
        elif applied is False:
            for field in ("deferred_reason", "deferred_approved_by"):
                if not _nonempty(steer.get(field)):
                    errors.append(f"{where}.{field}: required when a steer is not applied")
        gate_entry = gates.get(gate) if isinstance(gates, dict) and isinstance(gate, str) else None
        approved = parse_time(gate_entry.get("approved_at")) if isinstance(gate_entry, dict) else None
        at = parse_time(steer.get("at"))
        if approved and at and at > approved:
            errors.append(f"{where}.at: steer must be recorded before gates.{gate} approval")
    return by_id


def validate_checkpoints(manifest: dict, strict: bool, steers: dict[str, dict], errors: list, warnings: list) -> None:
    checkpoints = manifest.get("checkpoints")
    if checkpoints is None:
        if strict:
            for gate in CHECKPOINT_GATES:
                errors.append(
                    f"checkpoints.{gate}_draft: required at H3 (draft published >=10 min before the gate)"
                )
        return
    if not isinstance(checkpoints, dict):
        errors.append("checkpoints: expected an object")
        return
    gates = manifest.get("gates") or {}
    seen_steer_ids: set[str] = set()
    for gate in CHECKPOINT_GATES:
        key = f"{gate}_draft"
        checkpoint = checkpoints.get(key)
        if checkpoint is None:
            if strict:
                errors.append(f"checkpoints.{key}: required at H3")
            continue
        if not isinstance(checkpoint, dict):
            errors.append(f"checkpoints.{key}: must be an object")
            continue
        published = parse_time(checkpoint.get("published_at"))
        if published is None:
            errors.append(f"checkpoints.{key}.published_at: invalid timestamp")
        window = checkpoint.get("review_window_minutes")
        if isinstance(window, bool) or not isinstance(window, (int, float)) or window < CHECKPOINT_MINUTES:
            errors.append(
                f"checkpoints.{key}.review_window_minutes: must be >= {CHECKPOINT_MINUTES} minutes"
            )
        reviewers = checkpoint.get("reviewers")
        if not isinstance(reviewers, list) or not reviewers or not all(_nonempty(r) for r in reviewers):
            errors.append(f"checkpoints.{key}.reviewers: list of reviewer ids required")
        outcome = checkpoint.get("outcome")
        if outcome not in CHECKPOINT_OUTCOMES:
            errors.append(f"checkpoints.{key}.outcome: expected unchanged or steered")
        gate_entry = gates.get(gate)
        if isinstance(gate_entry, dict):
            requested = parse_time(gate_entry.get("requested_at"))
            if published and requested:
                delta = (requested - published).total_seconds() / 60
                if delta < CHECKPOINT_MINUTES:
                    errors.append(
                        f"checkpoints.{key}: draft must be published at least {CHECKPOINT_MINUTES} "
                        f"minutes before gates.{gate}.requested_at (got {delta:.0f} min)"
                    )
            approved = parse_time(gate_entry.get("approved_at"))
            if published and approved and published > approved:
                errors.append(f"checkpoints.{key}.published_at: must precede gates.{gate}.approved_at")
        steer_ids = checkpoint.get("steer_ids") or []
        if not isinstance(steer_ids, list):
            errors.append(f"checkpoints.{key}.steer_ids: expected a list")
            steer_ids = []
        if outcome == "steered":
            if not steer_ids:
                errors.append(f"checkpoints.{key}.steer_ids: required when outcome is steered")
            for sid in steer_ids:
                steer = steers.get(sid)
                if steer is None:
                    errors.append(f"checkpoints.{key}.steer_ids: unknown steer {sid!r}; add it to steers")
                    continue
                if steer.get("gate") != gate:
                    errors.append(f"checkpoints.{key}.steer_ids: steer {sid} belongs to {steer.get('gate')}")
                seen_steer_ids.add(sid)
        elif steer_ids:
            errors.append(f"checkpoints.{key}.steer_ids: must be empty when outcome is unchanged")
        else:
            for sid, steer in steers.items():
                if steer.get("gate") == gate:
                    errors.append(
                        f"checkpoints.{key}.outcome: steer {sid} exists for {gate} but the draft was unchanged"
                    )
    for sid, steer in steers.items():
        if sid not in seen_steer_ids:
            errors.append(f"steers.{sid}: not linked from a checkpoints.*_draft entry")
        if steer.get("gate") not in CHECKPOINT_GATES:
            errors.append(f"steers.{sid}.gate: no checkpoint for {steer.get('gate')!r}")


def validate_touchpoints(manifest: dict, strict: bool, errors: list, warnings: list) -> None:
    touchpoints = manifest.get("touchpoints")
    if touchpoints is None:
        (errors if strict else warnings).append(
            "touchpoints: required at H3 (Lead may only contact humans at six touchpoints)"
        )
        return
    if not isinstance(touchpoints, list):
        errors.append("touchpoints: expected a list")
        return
    lane = str(manifest.get("lane") or "standard").lower()
    if lane not in LANES:
        errors.append(f"lane: expected one of {', '.join(LANES)}, got {lane!r}")
        lane = "standard"
    caps = TOUCHPOINT_CAPS[lane]
    counts = {kind: 0 for kind in TOUCHPOINT_KINDS}
    gates_seen: list[str] = []
    for i, entry in enumerate(touchpoints):
        where = f"touchpoints[{i}]"
        if not isinstance(entry, dict):
            errors.append(f"{where}: must be an object")
            continue
        kind = entry.get("kind")
        if kind not in TOUCHPOINT_KINDS:
            errors.append(f"{where}.kind: expected one of {', '.join(TOUCHPOINT_KINDS)}")
            continue
        counts[kind] += 1
        if not _timestamp(entry.get("at")):
            errors.append(f"{where}.at: invalid timestamp")
        if not _nonempty(entry.get("actor")):
            errors.append(f"{where}.actor: required (who was contacted)")
        if kind == "gates":
            gate = entry.get("gate")
            expected = (QUICK_GATE,) if lane == "quick" else GATE_ORDER
            if gate not in expected:
                errors.append(f"{where}.gate: expected {', '.join(expected)} for the {lane} lane")
            elif gate in gates_seen:
                errors.append(f"{where}.gate: duplicate gate touchpoint {gate}")
            else:
                gates_seen.append(gate)
        if kind == "exception" and not _nonempty(entry.get("reason")):
            errors.append(f"{where}.reason: required for an exception touchpoint")
    for kind, cap in caps.items():
        if counts[kind] > cap:
            errors.append(f"touchpoints: {kind} used {counts[kind]} time(s); budget is {cap}")
    if strict:
        if "intake" not in {e.get("kind") for e in touchpoints if isinstance(e, dict)}:
            errors.append("touchpoints: intake record required at H3")
        expected_gates = [QUICK_GATE] if lane == "quick" else list(GATE_ORDER)
        missing = [gate for gate in expected_gates if gate not in gates_seen]
        if missing:
            errors.append(f"touchpoints: missing gate touchpoint(s) {', '.join(missing)}")
        if lane == "program" and counts["contract"] == 0:
            errors.append("touchpoints: Program requires a contract touchpoint (split/contract approval)")


def validate_policy(manifest: dict, profile: str) -> tuple[list, list]:
    """Validate the v4.3 policy blocks. Strict at H3, advisory before it."""
    strict = profile == "h3"
    errors: list[str] = []
    warnings: list[str] = []
    validate_artifacts(manifest, strict, errors, warnings)
    if manifest.get("program_child") is True:
        # A Program child only budgets its own deliverables; gates, checkpoints,
        # steer ledger, security overlay and touchpoints belong to the parent.
        return errors, warnings
    validate_security_overlay(manifest, strict, errors, warnings)
    steers = validate_steers(manifest, strict, errors, warnings)
    validate_checkpoints(manifest, strict, steers, errors, warnings)
    validate_touchpoints(manifest, strict, errors, warnings)
    return errors, warnings


MATRIX_ROWS = (
    ("R0 / R1", "1–3", "任意产物：issue 记录、PR、测试证据即可；不强制 HTML"),
    ("R2", "3", "需求分析、方案设计、测试设计与用例（三份，不多不少）"),
    ("R3", "≥6", "五份固定文档 + 安全 overlay；触发原型时再加交互原型"),
    ("Program 子级", "1–2", "开发交付说明 + 至多一份需求/设计摘要；验收并入父级"),
)


def cmd_check(args) -> int:
    manifest = load_manifest(Path(args.manifest))
    errors, warnings = validate_policy(manifest, args.profile)
    if args.json:
        print(json.dumps({
            "ok": not errors,
            "profile": args.profile,
            "issue": manifest.get("issue"),
            "errors": errors,
            "warnings": warnings,
        }, ensure_ascii=False, indent=2))
    elif errors:
        print("POLICY: FAIL")
        for error in errors:
            print("  ERROR:", error)
        for warning in warnings:
            print("  WARN:", warning)
    else:
        print("POLICY: OK")
        print(f"  issue: {manifest.get('issue')}")
        print(f"  risk: {manifest.get('risk')}")
        print(f"  profile: {args.profile}")
        for warning in warnings:
            print("  WARN:", warning)
    return 1 if errors else 0


def cmd_matrix(_args) -> int:
    width = max(len(row[0]) for row in MATRIX_ROWS)
    print("风险分级产物矩阵（每变更集）")
    for tier, budget, detail in MATRIX_ROWS:
        print(f"  {tier:<{width}}  上限 {budget:<4}  {detail}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="KAR v4.3 governance policy checks")
    sub = ap.add_subparsers(dest="command", required=True)
    p_check = sub.add_parser("check", help="Validate the v4.3 policy blocks of a manifest")
    p_check.add_argument("--manifest", required=True)
    p_check.add_argument("--profile", choices=("draft", "freeze", "h3"), default="h3")
    p_check.add_argument("--json", action="store_true")
    p_check.set_defaults(func=cmd_check)
    p_matrix = sub.add_parser("matrix", help="Print the risk-tier artifact matrix")
    p_matrix.set_defaults(func=cmd_matrix)
    return ap


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
