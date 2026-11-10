#!/usr/bin/env python3
"""v4.4 governance policy checks for a KAR delivery manifest.

The P1/P2 controls introduced in v4.3 and v4.4 live here so they can be tested and
run on their own:

* artifact matrix    - how many formal deliverables each risk tier may spend
* security overlay   - R3 threat model, permission matrix, scans, rollback drill
* draft checkpoints  - H1/H2 drafts published at least 10 minutes before the gate
* steer ledger       - corrections made during draft review are recorded
* touchpoint budget  - the Lead may only touch humans at six contact points
* low-risk autonomy   - R0/R1 reversible changes may assume agreement after 24h
* visual regression   - UI-affected changes carry a passing visual summary

Only the Python standard library is used. ``manifest.py check --profile h3``
calls :func:`validate_policy`, so a manifest cannot pass H3 while violating
these rules. Run ``policy.py check`` for a fast, file-free audit.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import timedelta
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

# --- v4.4 low-risk autonomy ------------------------------------------------

AUTONOMY_RISKS = ("R0", "R1")
AUTONOMY_STATES = ("assumed", "approved", "overridden")
AUTONOMY_OVERRIDE_DECISIONS = ("rejected", "human_gate_restored")
AUTONOMY_MIN_WINDOW_HOURS = 24

# --- v4.4 visual regression ------------------------------------------------

VISUAL_THEME_DEFAULT = "light"


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


def _is_ratio(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 1


def validate_autonomy(manifest: dict, strict: bool, errors: list, warnings: list) -> None:
    """v4.4: R0/R1 reversible changes may assume agreement after a 24h window.

    The autonomy block records a *completed* 24h window. ``state`` says what
    the human then did: ``assumed`` (no answer, H1 recorded as assumed),
    ``approved`` (the human approved after the window) or ``overridden``
    (the human rejected the assumption; H3 must wait for rework and a human
    gate). H3 itself can never be replaced by an assumption.
    """
    block = manifest.get("autonomy")
    gates = manifest.get("gates") if isinstance(manifest.get("gates"), dict) else {}
    h1 = gates.get("h1") if isinstance(gates.get("h1"), dict) else {}
    if block is None:
        if h1.get("status") == "assumed":
            errors.append("autonomy: required when gates.h1.status is assumed")
        return
    if not isinstance(block, dict):
        errors.append("autonomy: expected an object")
        return

    risk = str(manifest.get("risk") or "").upper()
    if risk not in AUTONOMY_RISKS:
        errors.append(
            f"autonomy: only R0/R1 may use the 24h default, got {risk or 'unknown risk'}"
        )
    if manifest.get("program_child") is True:
        errors.append("autonomy: Program children inherit the parent's gates; do not record a child assumption")

    opt_in = block.get("project_opt_in")
    if not isinstance(opt_in, dict):
        errors.append("autonomy.project_opt_in: required object (by/at/scope; project-level human opt-in)")
    else:
        if not _nonempty(opt_in.get("by")):
            errors.append("autonomy.project_opt_in.by: required (the human who opted in)")
        if not _timestamp(opt_in.get("at")):
            errors.append("autonomy.project_opt_in.at: invalid timestamp")
        if not _nonempty(opt_in.get("scope")):
            errors.append("autonomy.project_opt_in.scope: required (project/repo scope)")

    if block.get("reversible") is not True:
        errors.append("autonomy.reversible: must be explicitly true (only reversible changes qualify)")
    if block.get("external_contract") is not False:
        errors.append("autonomy.external_contract: must be explicitly false (no external contract)")

    window = block.get("window_hours")
    window_ok = (
        isinstance(window, (int, float))
        and not isinstance(window, bool)
        and window >= AUTONOMY_MIN_WINDOW_HOURS
    )
    if not window_ok:
        errors.append(
            f"autonomy.window_hours: must be >= {AUTONOMY_MIN_WINDOW_HOURS} hours"
        )

    wait_started = parse_time(block.get("wait_started_at"))
    if wait_started is None:
        errors.append("autonomy.wait_started_at: invalid timestamp (when the H1 card was sent)")
    assumed_at = parse_time(block.get("assumed_at"))
    if assumed_at is None:
        errors.append("autonomy.assumed_at: invalid timestamp (when the 24h window elapsed)")

    notification = block.get("notification")
    reminder = None
    if not isinstance(notification, dict):
        errors.append("autonomy.notification: required object (single 24h reminder: at/actor/channel)")
    else:
        reminder = parse_time(notification.get("at"))
        if reminder is None:
            errors.append("autonomy.notification.at: invalid timestamp")
        if not _nonempty(notification.get("actor")):
            errors.append("autonomy.notification.actor: required (who was reminded)")
        if not _nonempty(notification.get("channel")):
            errors.append("autonomy.notification.channel: required (issue comment, etc.)")

    assumption = block.get("assumption")
    recorded = None
    if not isinstance(assumption, dict):
        errors.append("autonomy.assumption: required object (statement/owner/recorded_at)")
    else:
        statement = assumption.get("statement")
        if not _nonempty(statement):
            errors.append("autonomy.assumption.statement: required (the assumption being made)")
        elif len(statement.strip()) > 280:
            errors.append("autonomy.assumption.statement: keep to one line (<=280 chars)")
        if not _nonempty(assumption.get("owner")):
            errors.append("autonomy.assumption.owner: required (the Decision Owner)")
        recorded = parse_time(assumption.get("recorded_at"))
        if recorded is None:
            errors.append("autonomy.assumption.recorded_at: invalid timestamp")
        if assumption.get("expires_at") is not None:
            expires = parse_time(assumption.get("expires_at"))
            if expires is None:
                errors.append("autonomy.assumption.expires_at: invalid timestamp")
            elif recorded and expires <= recorded:
                errors.append("autonomy.assumption.expires_at: must be after recorded_at")

    state = block.get("state")
    if state not in AUTONOMY_STATES:
        errors.append(f"autonomy.state: expected one of {', '.join(AUTONOMY_STATES)}")

    if wait_started and window_ok and assumed_at:
        window_end = wait_started + timedelta(hours=float(window))
        if assumed_at < window_end:
            errors.append(
                "autonomy.assumed_at: the 24h window has not elapsed "
                f"(wait_started_at + {window:g}h)"
            )
        if reminder is not None and reminder < window_end:
            errors.append("autonomy.notification.at: the single reminder may not precede the 24h window")
    if wait_started and reminder is not None and reminder < wait_started:
        errors.append("autonomy.notification.at: must not precede autonomy.wait_started_at")
    if assumed_at and reminder is not None and reminder > assumed_at:
        errors.append("autonomy.notification.at: reminder must be recorded at or before assumed_at")

    if state == "assumed":
        if h1.get("status") != "assumed":
            errors.append("autonomy.state=assumed: requires gates.h1.status=assumed")
        elif parse_time(h1.get("assumed_at")) != assumed_at:
            errors.append("autonomy.assumed_at: must equal gates.h1.assumed_at")
        if h1.get("approver_type") != "assumption":
            errors.append("gates.h1.approver_type: expected assumption when H1 is assumed")
    elif state == "approved":
        if h1.get("status") != "approved":
            errors.append("autonomy.state=approved: requires gates.h1.status=approved (human)")
        approved_at = parse_time(h1.get("approved_at"))
        if approved_at and assumed_at and approved_at < assumed_at:
            errors.append(
                "gates.h1.approved_at: a normal early H1 approval should not carry an autonomy block; "
                "record it after the 24h assumption instead"
            )
    elif state == "overridden":
        if h1.get("status") == "assumed":
            errors.append("gates.h1: must not stay assumed after a human override")
        message = (
            "autonomy.state=overridden: the human rejected the assumption; restore H1 and rework before H3"
        )
        if strict:
            errors.append(message)
        else:
            warnings.append(message)

    override = block.get("override")
    if state == "overridden" and override is None:
        errors.append("autonomy.override: required when state is overridden (by/at/decision/reason)")
    if override is not None:
        if not isinstance(override, dict):
            errors.append("autonomy.override: expected an object")
        else:
            if not _nonempty(override.get("by")):
                errors.append("autonomy.override.by: required (the human who overrode)")
            overridden_at = parse_time(override.get("at"))
            if overridden_at is None:
                errors.append("autonomy.override.at: invalid timestamp")
            elif assumed_at and overridden_at < assumed_at:
                errors.append("autonomy.override.at: cannot precede the assumption")
            if not _nonempty(override.get("reason")):
                errors.append("autonomy.override.reason: required")
            decision = override.get("decision")
            if decision not in AUTONOMY_OVERRIDE_DECISIONS:
                errors.append(
                    "autonomy.override.decision: expected rejected or human_gate_restored"
                )
            if decision == "rejected" and state != "overridden":
                errors.append("autonomy.override.decision=rejected: state must be overridden")
            if decision == "human_gate_restored":
                if state != "approved":
                    errors.append(
                        "autonomy.override.decision=human_gate_restored: H1 must be human-approved before H3"
                    )
                if h1.get("status") != "approved":
                    errors.append("gates.h1: human_gate_restored requires a human H1 approval")


def validate_visual_regression(manifest: dict, strict: bool, errors: list, warnings: list) -> None:
    """v4.4: UI-affected changes must carry a passing visual-regression summary.

    The summary is a pointer + coverage proof; ``visual.py check`` validates the
    project's own config/results file (tool, breakpoints, thresholds, coverage).
    """
    ui = manifest.get("ui_affected")
    if ui is not None and not isinstance(ui, bool):
        errors.append("ui_affected: expected true or false")
    block = manifest.get("visual_regression")
    if manifest.get("program_child") is True:
        if block is not None:
            warnings.append("visual_regression: Program children inherit the parent's visual evidence")
        return
    if block is None:
        if strict and ui is True:
            errors.append(
                "visual_regression: required at H3 when ui_affected is true "
                "(config/tool/breakpoints/thresholds/results)"
            )
        return
    if not isinstance(block, dict):
        errors.append("visual_regression: expected an object")
        return
    if ui is not True:
        warnings.append("visual_regression: only required when ui_affected is true; recorded anyway")

    _check_doc_entry(block, "config", errors, prefix="visual_regression")
    if not _nonempty(block.get("tool")):
        errors.append("visual_regression.tool: required (the tool that produced the results)")

    breakpoints = block.get("breakpoints")
    names: list[str] = []
    if not isinstance(breakpoints, list) or not breakpoints:
        errors.append("visual_regression.breakpoints: non-empty list of breakpoint names required")
    else:
        for i, name in enumerate(breakpoints):
            if not _nonempty(name):
                errors.append(f"visual_regression.breakpoints[{i}]: expected a non-empty name")
            elif name in names:
                errors.append(f"visual_regression.breakpoints[{i}]: duplicate breakpoint {name!r}")
            else:
                names.append(name)

    themes = block.get("themes")
    theme_names: list[str] = []
    if themes is not None:
        if not isinstance(themes, list) or not themes:
            errors.append("visual_regression.themes: expected a non-empty list when set")
        else:
            for i, theme in enumerate(themes):
                if not _nonempty(theme):
                    errors.append(f"visual_regression.themes[{i}]: expected a non-empty name")
                elif theme in theme_names:
                    errors.append(f"visual_regression.themes[{i}]: duplicate theme {theme!r}")
                else:
                    theme_names.append(theme)

    thresholds = block.get("thresholds")
    max_ratio = critical_ratio = None
    if not isinstance(thresholds, dict):
        errors.append("visual_regression.thresholds: required object (max_diff_ratio, critical_max_diff_ratio)")
    else:
        max_ratio = thresholds.get("max_diff_ratio")
        if not _is_ratio(max_ratio):
            errors.append("visual_regression.thresholds.max_diff_ratio: required number in [0, 1]")
            max_ratio = None
        critical_ratio = thresholds.get("critical_max_diff_ratio")
        if critical_ratio is not None and not _is_ratio(critical_ratio):
            errors.append("visual_regression.thresholds.critical_max_diff_ratio: number in [0, 1]")
            critical_ratio = None
        elif critical_ratio is not None and max_ratio is not None and critical_ratio > max_ratio:
            errors.append(
                "visual_regression.thresholds.critical_max_diff_ratio: must not exceed max_diff_ratio"
            )

    results = block.get("results")
    if not isinstance(results, list) or not results:
        errors.append("visual_regression.results: non-empty list of screen results required")
    else:
        for i, entry in enumerate(results):
            where = f"visual_regression.results[{i}]"
            if not isinstance(entry, dict):
                errors.append(f"{where}: must be an object")
                continue
            if not _nonempty(entry.get("screen")):
                errors.append(f"{where}.screen: required")
            breakpoint = entry.get("breakpoint")
            if not _nonempty(breakpoint):
                errors.append(f"{where}.breakpoint: required")
            elif names and breakpoint not in names:
                errors.append(f"{where}.breakpoint: unknown breakpoint {breakpoint!r}")
            theme = entry.get("theme")
            if theme is not None and not _nonempty(theme):
                errors.append(f"{where}.theme: must be a non-empty string when set")
            elif theme and theme_names and theme not in theme_names:
                errors.append(f"{where}.theme: unknown theme {theme!r}")
            diff = entry.get("diff_ratio")
            if not _is_ratio(diff):
                errors.append(f"{where}.diff_ratio: required number in [0, 1]")
                continue
            critical = entry.get("critical")
            if critical is not None and not isinstance(critical, bool):
                errors.append(f"{where}.critical: expected true or false")
            limit = critical_ratio if (critical is True and critical_ratio is not None) else max_ratio
            if limit is not None and diff > limit:
                errors.append(
                    f"{where}.diff_ratio: {diff} exceeds the "
                    f"{'critical ' if critical is True else ''}threshold {limit}"
                )

    passed = block.get("passed")
    if not isinstance(passed, bool):
        errors.append("visual_regression.passed: expected true or false")
    elif strict and passed is not True:
        errors.append("visual_regression.passed: visual comparison must pass at H3")
    if not _timestamp(block.get("at")):
        errors.append("visual_regression.at: invalid timestamp")


def validate_policy(manifest: dict, profile: str) -> tuple[list, list]:
    """Validate the policy blocks. Strict at H3, advisory before it."""
    strict = profile == "h3"
    errors: list[str] = []
    warnings: list[str] = []
    validate_artifacts(manifest, strict, errors, warnings)
    validate_autonomy(manifest, strict, errors, warnings)
    validate_visual_regression(manifest, strict, errors, warnings)
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
    ap = argparse.ArgumentParser(description="KAR v4.4 governance policy checks")
    sub = ap.add_subparsers(dest="command", required=True)
    p_check = sub.add_parser("check", help="Validate the v4.3/v4.4 policy blocks of a manifest")
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
