#!/usr/bin/env python3
"""Freeze and check a KAR delivery manifest (v4.3).

Commands:
  digest  Print (and optionally write) the candidate digest/tag.
  freeze  Validate the recorded facts, then write candidate.digest/tag.
  check   Validate a manifest: docs SHA, prototype SHA, repo head, PR, CI,
          candidate tag, gates, R3 second review, H3 sampling and metrics.
  policy  (v4.3)  is validated by policy.py: artifact matrix, R3 security
          overlay, draft checkpoints/steer ledger and the Lead touchpoint budget.

Only the Python standard library is used. ``check`` is offline by default;
pass --check-remotes / --check-prs / --check-ci to compare against Git
remotes and GitHub (gh CLI).
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

from kar_common import (
    CHECK_RESULTS,
    GATE_CHECKS,
    GATE_ORDER,
    GATE_STATUS,
    H3_SAMPLE_RATE,
    METRIC_KEYS,
    candidate_digest,
    candidate_tag,
    git_head,
    iso,
    load_manifest,
    normalize_number,
    parse_time,
    run_cmd,
    sha256_file,
    utcnow,
)
from policy import validate_policy

PR_RE = re.compile(r"^(https?://\S+/pull/\d+|#?\d+)$")
CI_STATUSES = ("passed", "failed", "pending", "running")
REQUIRED_DOCS = ("requirements", "design", "test_design", "dev_notes")
H3_REQUIRED_DOCS = REQUIRED_DOCS + ("qa_report",)


def _nonempty(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _resolve(path_text: str, root: Path) -> Path:
    path = Path(path_text)
    return path if path.is_absolute() else root / path


def validate_docs(manifest: dict, docs_root: Path, verify_files: bool, required: tuple, errors: list, warnings: list) -> None:
    docs = manifest.get("docs")
    if not isinstance(docs, dict) or not docs:
        errors.append("docs: missing or not an object")
        return
    for key in required:
        if key not in docs:
            errors.append(f"docs.{key}: required entry missing")
    prototype = docs.get("prototype")
    for key, entry in docs.items():
        if not isinstance(entry, dict):
            errors.append(f"docs.{key}: must be an object")
            continue
        if not _nonempty(entry.get("path")):
            errors.append(f"docs.{key}.path: required")
            continue
        if not _nonempty(entry.get("version")):
            errors.append(f"docs.{key}.version: required")
        sha = entry.get("sha")
        if not _nonempty(sha) or not re.fullmatch(r"[0-9a-f]{64}", str(sha)):
            errors.append(f"docs.{key}.sha: expected 64-char lowercase hex")
            continue
        if not verify_files:
            continue
        path = _resolve(entry["path"], docs_root)
        if not path.is_file():
            errors.append(f"docs.{key}: file not found: {path}")
            continue
        actual = sha256_file(path)
        if actual != sha:
            errors.append(f"docs.{key}: sha mismatch (manifest {sha[:12]}, file {actual[:12]}); late doc change")
    if isinstance(prototype, dict):
        if prototype.get("mode") not in (None, "A", "B"):
            errors.append("docs.prototype.mode: expected A or B")
        if verify_files:
            if prototype.get("mode") not in ("A", "B"):
                errors.append("docs.prototype.mode: required for H1 binding")
            for field in ("approved_by", "approved_at"):
                if not _nonempty(prototype.get(field)):
                    errors.append(f"docs.prototype.{field}: required for H1 binding")
            if prototype.get("approved_at") and not parse_time(prototype.get("approved_at")):
                errors.append("docs.prototype.approved_at: invalid timestamp")


def validate_repos(
    manifest: dict,
    profile: str,
    repo_roots: dict,
    check_remotes: bool,
    errors: list,
    warnings: list,
) -> dict[str, str]:
    repos = manifest.get("repos")
    if not isinstance(repos, list) or not repos:
        errors.append("repos: at least one repository entry is required")
        return {}
    verify = profile in ("freeze", "h3")
    seen_ids = set()
    seen_orders = set()
    heads: dict[str, str] = {}
    for i, repo in enumerate(repos):
        where = f"repos[{i}]"
        if not isinstance(repo, dict):
            errors.append(f"{where}: must be an object")
            continue
        repo_id = repo.get("repo_id")
        if not _nonempty(repo_id):
            errors.append(f"{where}.repo_id: required")
            continue
        if repo_id in seen_ids:
            errors.append(f"{where}.repo_id: duplicate {repo_id}")
        seen_ids.add(repo_id)
        for field in ("base", "branch", "head"):
            if not _nonempty(repo.get(field)):
                errors.append(f"{where}.{field}: required")
        head = str(repo.get("head") or "")
        if head and not re.fullmatch(r"[0-9a-f]{40}", head):
            errors.append(f"{where}.head: expected 40-char lowercase git SHA")
        order = repo.get("merge_order")
        if isinstance(order, bool) or not isinstance(order, int) or order < 1:
            errors.append(f"{where}.merge_order: positive integer required")
        elif order in seen_orders:
            errors.append(f"{where}.merge_order: duplicate {order}")
        else:
            seen_orders.add(order)
        pr = repo.get("pr")
        if not _nonempty(pr):
            if verify:
                errors.append(f"{where}.pr: required")
            else:
                warnings.append(f"{where}.pr: missing (fine for a draft)")
        elif not PR_RE.fullmatch(str(pr).strip()):
            errors.append(f"{where}.pr: expected a pull request URL or number, got {pr!r}")
        ci = repo.get("ci")
        if not isinstance(ci, dict):
            if verify:
                errors.append(f"{where}.ci: required object with status/head/url/checked_at")
            else:
                warnings.append(f"{where}.ci: missing (fine for a draft)")
        else:
            status = ci.get("status")
            if status not in CI_STATUSES:
                errors.append(f"{where}.ci.status: expected one of {', '.join(CI_STATUSES)}")
            if ci.get("head") != head:
                errors.append(f"{where}.ci.head: must equal repos[i].head")
            if not _nonempty(ci.get("url")):
                errors.append(f"{where}.ci.url: required")
            if not parse_time(ci.get("checked_at")):
                errors.append(f"{where}.ci.checked_at: invalid timestamp")
            if verify and status != "passed":
                errors.append(f"{where}.ci: candidate requires CI passed, got {status!r}")
        if not verify:
            continue
        root = repo_roots.get(repo_id)
        if root is None:
            errors.append(f"{where}: no --repo-root {repo_id}=<path> given; cannot verify head")
            continue
        try:
            actual = git_head(root)
        except (RuntimeError, OSError) as exc:
            errors.append(f"{where}: cannot read git head: {exc}")
            continue
        heads[repo_id] = actual
        if actual != head:
            errors.append(
                f"{where}: LATE PUSH — manifest head {head[:12]}, {repo_id} is at {actual[:12]}; "
                "candidate is stale, re-run check after a new freeze"
            )
        if check_remotes:
            remote = repo.get("remote")
            if not _nonempty(remote):
                warnings.append(f"{where}.remote: not set; skipped remote head check")
            else:
                branch = str(repo.get("branch") or "")
                proc = run_cmd(["git", "ls-remote", str(remote), f"refs/heads/{branch}"])
                if proc.returncode != 0:
                    errors.append(f"{where}: git ls-remote failed: {proc.stderr.strip()}")
                else:
                    lines = [line for line in proc.stdout.splitlines() if line.strip()]
                    remote_head = lines[0].split()[0] if lines else ""
                    if remote_head != head:
                        errors.append(
                            f"{where}: LATE PUSH — remote {branch} is {remote_head[:12] or 'missing'}, "
                            f"manifest records {head[:12]}"
                        )
    return heads


def _gh_json(gh: str, args: list[str], label: str, errors: list):
    proc = run_cmd([gh] + args)
    if proc.returncode != 0:
        errors.append(f"{label}: gh failed: {proc.stderr.strip() or proc.stdout.strip()}")
        return None
    try:
        return json.loads(proc.stdout or "null")
    except json.JSONDecodeError:
        errors.append(f"{label}: gh returned non-JSON output")
        return None


def validate_external(repos: list, gh: str, check_prs: bool, check_ci: bool, errors: list, warnings: list) -> None:
    for i, repo in enumerate(repos):
        if not isinstance(repo, dict):
            continue
        pr = str(repo.get("pr") or "").strip()
        label = f"repos[{i}] ({repo.get('repo_id')})"
        if check_prs and pr:
            data = _gh_json(gh, ["pr", "view", pr, "--json", "headRefOid,state,url"], f"{label} PR", errors)
            if isinstance(data, dict):
                if data.get("headRefOid") != repo.get("head"):
                    errors.append(
                        f"{label}: PR head {str(data.get('headRefOid'))[:12]} != manifest head "
                        f"{str(repo.get('head'))[:12]}; late push"
                    )
                if data.get("state") not in ("OPEN", None):
                    errors.append(f"{label}: PR state is {data.get('state')}, expected OPEN")
        if check_ci and pr:
            data = _gh_json(gh, ["pr", "checks", pr, "--json", "name,state,bucket,link"], f"{label} CI", errors)
            if isinstance(data, list):
                if not data:
                    errors.append(f"{label}: CI has no checks")
                else:
                    failing = [c for c in data if c.get("bucket") != "pass"]
                    if failing:
                        names = ", ".join(str(c.get("name")) for c in failing)
                        errors.append(f"{label}: CI not green ({names})")
            elif data is not None:
                errors.append(f"{label}: CI check output is not a list")


def validate_candidate(manifest: dict, required: bool, errors: list, warnings: list) -> str | None:
    digest = candidate_digest(manifest)
    candidate = manifest.get("candidate")
    if not isinstance(candidate, dict):
        if required:
            errors.append("candidate: missing; run `manifest.py freeze --write`")
        return None
    recorded = candidate.get("digest")
    if not _nonempty(recorded):
        if required:
            errors.append("candidate.digest: required")
    elif recorded != digest:
        errors.append(
            f"candidate: STALE — recorded digest {recorded} != rebuilt {digest}; "
            "a doc, branch or head changed after freeze"
        )
    expected_tag = candidate_tag(manifest, digest)
    tag = candidate.get("tag")
    if not _nonempty(tag):
        if required:
            errors.append("candidate.tag: required")
    elif tag != expected_tag:
        errors.append(f"candidate.tag: expected {expected_tag}, got {tag}")
    if not parse_time(candidate.get("frozen_at")):
        if required:
            errors.append("candidate.frozen_at: required timestamp")
        else:
            warnings.append("candidate.frozen_at: missing timestamp")
    return digest


def validate_gates(manifest: dict, profile: str, errors: list, warnings: list) -> None:
    gates = manifest.get("gates")
    strict = profile == "h3"
    if not isinstance(gates, dict) or not gates:
        if strict:
            errors.append("gates: missing or not an object")
        else:
            warnings.append("gates: not recorded yet (fine before H3)")
        return
    if strict:
        for key in GATE_ORDER:
            if key not in gates:
                errors.append(f"gates.{key}: required at H3")
    for key, gate in gates.items():
        if key not in GATE_CHECKS:
            warnings.append(f"gates.{key}: unknown gate ignored")
            continue
        if not isinstance(gate, dict):
            errors.append(f"gates.{key}: must be an object")
            continue
        status = gate.get("status")
        if status not in GATE_STATUS:
            errors.append(f"gates.{key}.status: expected one of {', '.join(GATE_STATUS)}")
        if strict and status != "approved":
            errors.append(f"gates.{key}: must be approved at H3, got {status!r}")
        checks = gate.get("checks")
        if checks is not None:
            expected = [check_id for check_id, _ in GATE_CHECKS[key]]
            if not isinstance(checks, list) or len(checks) != 3:
                errors.append(f"gates.{key}.checks: exactly 3 checks required")
            else:
                ids = [c.get("id") for c in checks if isinstance(c, dict)]
                if sorted(ids) != sorted(expected):
                    errors.append(f"gates.{key}.checks: expected ids {expected}, got {ids}")
                for c in checks:
                    if not isinstance(c, dict):
                        errors.append(f"gates.{key}.checks: entries must be objects")
                        continue
                    cid = c.get("id")
                    if c.get("result") not in CHECK_RESULTS:
                        errors.append(f"gates.{key}.{cid}.result: expected {', '.join(CHECK_RESULTS)}")
                    if c.get("result") == "fail":
                        errors.append(f"gates.{key}.{cid}: check failed")
                    if not _nonempty(c.get("evidence")):
                        errors.append(f"gates.{key}.{cid}.evidence: required")
                    if c.get("result") == "n/a" and not _nonempty(c.get("note")):
                        warnings.append(f"gates.{key}.{cid}: n/a without note")
        elif strict and status == "approved":
            errors.append(f"gates.{key}.checks: 3 checks required before approval")
        rationale = gate.get("rationale")
        if _nonempty(rationale) and len(rationale.strip()) > 280:
            errors.append(f"gates.{key}.rationale: keep to one sentence (<=280 chars)")
        conditions = gate.get("conditions")
        if conditions is not None and not isinstance(conditions, list):
            errors.append(f"gates.{key}.conditions: expected a list")
        if status == "approved":
            if strict and not _nonempty(rationale):
                errors.append(f"gates.{key}.rationale: one-sentence reason required")
            if strict and conditions is None:
                errors.append(f"gates.{key}.conditions: required (use [] when none)")
            if gate.get("approver_type") != "human":
                errors.append(f"gates.{key}.approver_type: approval must be human, got {gate.get('approver_type')!r}")
            if not _nonempty(gate.get("approved_by")):
                errors.append(f"gates.{key}.approved_by: required")
            if not parse_time(gate.get("approved_at")):
                errors.append(f"gates.{key}.approved_at: invalid timestamp")
        if status == "pending":
            if gate.get("approved_at"):
                errors.append(f"gates.{key}: pending gate has approved_at")
            if strict and not parse_time(gate.get("requested_at")):
                errors.append(f"gates.{key}.requested_at: required for pending gate")
        if status == "rejected" and not _nonempty(rationale):
            errors.append(f"gates.{key}.rationale: rejection reason required")

    h3 = gates.get("h3")
    if strict and isinstance(h3, dict):
        candidate = manifest.get("candidate") or {}
        if h3.get("candidate_digest") != candidate.get("digest"):
            errors.append("gates.h3.candidate_digest: must equal candidate.digest")
        risk = str(manifest.get("risk") or "").upper()
        if risk == "R3":
            second = h3.get("second_reviewer")
            if not isinstance(second, dict):
                errors.append("gates.h3.second_reviewer: required for R3")
            else:
                for field in ("reviewer", "role", "verdict", "at"):
                    if not _nonempty(second.get(field)):
                        errors.append(f"gates.h3.second_reviewer.{field}: required for R3")
                if second.get("verdict") not in (None, "pass"):
                    errors.append("gates.h3.second_reviewer.verdict: must be pass")
                if second.get("at") and not parse_time(second.get("at")):
                    errors.append("gates.h3.second_reviewer.at: invalid timestamp")
        validate_sampling(h3, errors)
        validate_metrics(manifest, errors)


def validate_sampling(h3: dict, errors: list) -> None:
    sampling = h3.get("sampling")
    if not isinstance(sampling, dict):
        errors.append("gates.h3.sampling: required record of the 10% gate sample")
        return
    rate = sampling.get("rate")
    if rate != H3_SAMPLE_RATE:
        errors.append(f"gates.h3.sampling.rate: expected {H3_SAMPLE_RATE}, got {rate!r}")
    population = sampling.get("population")
    if isinstance(population, bool) or not isinstance(population, int) or population < 1:
        errors.append("gates.h3.sampling.population: positive integer required")
        population = 1
    required_sample = max(1, math.ceil(H3_SAMPLE_RATE * population))
    sampled = sampling.get("sampled")
    if not isinstance(sampled, list) or not sampled:
        errors.append("gates.h3.sampling.sampled: list of reviewed gate ids required")
    elif len(sampled) < required_sample:
        errors.append(
            f"gates.h3.sampling.sampled: {len(sampled)} recorded, 10% of {population} requires {required_sample}"
        )
    else:
        for gate_id in sampled:
            if gate_id not in GATE_CHECKS:
                errors.append(f"gates.h3.sampling.sampled: unknown gate id {gate_id!r}")
    for field in ("reviewed_by", "at"):
        if not _nonempty(sampling.get(field)):
            errors.append(f"gates.h3.sampling.{field}: required")
    if sampling.get("at") and not parse_time(sampling.get("at")):
        errors.append("gates.h3.sampling.at: invalid timestamp")
    if not _nonempty(sampling.get("note")):
        errors.append("gates.h3.sampling.note: required (findings or 'no findings')")


def validate_metrics(manifest: dict, errors: list) -> None:
    metrics = manifest.get("metrics")
    if not isinstance(metrics, dict):
        errors.append("metrics: required at H3 (5 per-issue metrics)")
        return
    for key in METRIC_KEYS:
        if key not in metrics:
            errors.append(f"metrics.{key}: required")
            continue
        if normalize_number(metrics[key]) is None:
            errors.append(f"metrics.{key}: expected a non-negative number")
    closed = metrics.get("closed_at")
    if closed is not None and not parse_time(closed):
        errors.append("metrics.closed_at: invalid timestamp")


def validate(
    manifest: dict,
    *,
    profile: str,
    docs_root: Path,
    repo_roots: dict,
    check_remotes: bool = False,
    check_prs: bool = False,
    check_ci: bool = False,
    gh: str = "gh",
    require_candidate: bool | None = None,
) -> tuple[list, list]:
    errors: list[str] = []
    warnings: list[str] = []
    for field in ("version", "change_set_id", "issue", "slug"):
        if manifest.get(field) in (None, ""):
            errors.append(f"{field}: required")
    try:
        version = int(manifest.get("version"))
    except (TypeError, ValueError):
        version = 0
    if version != 2:
        errors.append(f"version: expected 2, got {manifest.get('version')!r}")
    risk = str(manifest.get("risk") or "").upper()
    if not risk and profile == "h3":
        errors.append("risk: required at H3 (R0–R3) so R3 second review can be enforced")
    if risk and risk not in ("R0", "R1", "R2", "R3"):
        errors.append(f"risk: expected R0–R3, got {manifest.get('risk')!r}")
    if not _nonempty(manifest.get("decision_owner")):
        if profile == "h3":
            errors.append("decision_owner: required at H3 for human WIP/SLA attribution")
        else:
            warnings.append("decision_owner: missing; human WIP/SLA cannot attribute pending gates")

    verify_files = profile in ("freeze", "h3")
    required_docs = H3_REQUIRED_DOCS if profile == "h3" else REQUIRED_DOCS
    validate_docs(manifest, docs_root, verify_files, required_docs, errors, warnings)
    validate_repos(manifest, profile, repo_roots, check_remotes, errors, warnings)
    if require_candidate is None:
        require_candidate = profile in ("freeze", "h3")
    validate_candidate(manifest, require_candidate, errors, warnings)
    validate_gates(manifest, profile, errors, warnings)
    policy_errors, policy_warnings = validate_policy(manifest, profile)
    errors.extend(policy_errors)
    warnings.extend(policy_warnings)
    if profile in ("freeze", "h3"):
        validate_external(manifest.get("repos") or [], gh, check_prs, check_ci, errors, warnings)
    return errors, warnings


def cmd_digest(args) -> int:
    manifest = load_manifest(Path(args.manifest))
    digest = candidate_digest(manifest)
    tag = candidate_tag(manifest, digest)
    if args.write:
        manifest.setdefault("candidate", {})
        manifest["candidate"]["digest"] = digest
        manifest["candidate"]["tag"] = tag
        manifest["candidate"].setdefault("frozen_at", iso(utcnow()))
        Path(args.manifest).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"digest={digest} tag={tag}")
    return 0


def cmd_freeze(args) -> int:
    path = Path(args.manifest)
    manifest = load_manifest(path)
    docs_root = Path(args.docs_root) if args.docs_root else path.parent
    repo_roots = parse_repo_roots(args.repo_root)
    # A re-freeze replaces the old tag; do not treat the previous candidate as stale.
    working = dict(manifest)
    working.pop("candidate", None)
    # freeze requires the same facts as A4 handoff: files, heads, green CI.
    errors, warnings = validate(
        working,
        profile="freeze",
        docs_root=docs_root,
        repo_roots=repo_roots,
        check_remotes=args.check_remotes,
        check_prs=args.check_prs,
        check_ci=args.check_ci,
        gh=args.gh,
        require_candidate=False,
    )
    if errors:
        print("FREEZE: FAIL")
        for error in errors:
            print("  ERROR:", error)
        for warning in warnings:
            print("  WARN:", warning)
        return 1
    digest = candidate_digest(manifest)
    tag = candidate_tag(manifest, digest)
    manifest.setdefault("candidate", {})
    manifest["candidate"]["digest"] = digest
    manifest["candidate"]["tag"] = tag
    manifest["candidate"]["frozen_at"] = iso(utcnow())
    if args.write:
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"FREEZE: OK  wrote {path}")
    else:
        print("FREEZE: OK  dry-run (pass --write to record)")
    print(f"  digest: {digest}")
    print(f"  tag: {tag}")
    for warning in warnings:
        print("  WARN:", warning)
    return 0


def parse_repo_roots(values) -> dict:
    roots = {}
    for value in values or []:
        if "=" not in value:
            raise SystemExit(f"--repo-root expects repo_id=path, got {value!r}")
        repo_id, path = value.split("=", 1)
        roots[repo_id] = Path(path)
    return roots


def cmd_check(args) -> int:
    path = Path(args.manifest)
    manifest = load_manifest(path)
    docs_root = Path(args.docs_root) if args.docs_root else path.parent
    errors, warnings = validate(
        manifest,
        profile=args.profile,
        docs_root=docs_root,
        repo_roots=parse_repo_roots(args.repo_root),
        check_remotes=args.check_remotes,
        check_prs=args.check_prs,
        check_ci=args.check_ci,
        gh=args.gh,
    )
    digest = candidate_digest(manifest)
    if args.json:
        print(json.dumps({
            "ok": not errors,
            "profile": args.profile,
            "issue": manifest.get("issue"),
            "digest": digest,
            "tag": candidate_tag(manifest, digest),
            "errors": errors,
            "warnings": warnings,
        }, ensure_ascii=False, indent=2))
    elif errors:
        print("MANIFEST: FAIL")
        for error in errors:
            print("  ERROR:", error)
        for warning in warnings:
            print("  WARN:", warning)
    else:
        print("MANIFEST: OK")
        print(f"  issue: {manifest.get('issue')}")
        print(f"  tag: {candidate_tag(manifest, digest)}")
        print(f"  profile: {args.profile}")
        for warning in warnings:
            print("  WARN:", warning)
    return 1 if errors else 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="KAR delivery manifest: freeze and check")
    sub = ap.add_subparsers(dest="command", required=True)

    def add_common(p):
        p.add_argument("--manifest", required=True, help="Path to delivery-manifest.json")
        p.add_argument("--docs-root", default="", help="Docs home root for relative docs paths (default: manifest dir)")
        p.add_argument("--repo-root", action="append", default=[], help="repo_id=checkout path (repeatable)")
        p.add_argument("--check-remotes", action="store_true", help="Compare heads with git ls-remote")
        p.add_argument("--check-prs", action="store_true", help="Compare PR head/state via gh")
        p.add_argument("--check-ci", action="store_true", help="Check PR CI via gh")
        p.add_argument("--gh", default="gh", help="gh executable (default: gh)")

    p_digest = sub.add_parser("digest", help="Print the rebuilt candidate digest/tag")
    p_digest.add_argument("--manifest", required=True)
    p_digest.add_argument("--write", action="store_true", help="Write digest/tag/frozen_at into the manifest")
    p_digest.set_defaults(func=cmd_digest)

    p_freeze = sub.add_parser("freeze", help="Validate facts and write candidate.digest/tag")
    add_common(p_freeze)
    p_freeze.add_argument("--write", action="store_true", help="Write candidate into the manifest (default: dry-run)")
    p_freeze.set_defaults(func=cmd_freeze)

    p_check = sub.add_parser("check", help="Validate a manifest")
    add_common(p_check)
    p_check.add_argument("--profile", choices=("draft", "freeze", "h3"), default="freeze")
    p_check.add_argument("--json", action="store_true")
    p_check.set_defaults(func=cmd_check)
    return ap


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
