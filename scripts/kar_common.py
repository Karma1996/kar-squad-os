#!/usr/bin/env python3
"""Shared helpers for the KAR manifest / metrics / WIP scripts.

Only the Python standard library is used so the scripts run in the migration
package without extra dependencies.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

MANIFEST_NAME = "delivery-manifest.json"

# Inputs that define a candidate. qa_report is an output of verifying the
# candidate, so updating it must not change the candidate digest.
DIGEST_DOC_KEYS = ("requirements", "prototype", "design", "test_design", "dev_notes")

METRIC_KEYS = (
    "human_touches",
    "wait_human",
    "rework_rounds",
    "candidate_recuts",
    "escaped_defects",
)
WEEKLY_METRIC_KEYS = METRIC_KEYS + ("cycle_time_hours",)

GATE_CHECKS = {
    "h1": (
        ("scope", "范围与验收标准同需求版本一致"),
        ("prototype", "原型版本/SHA 与 manifest 一致（无原型记 n/a）"),
        ("evidence", "证据可复现，无未关闭 S0–S2"),
    ),
    "h2": (
        ("design", "设计覆盖全部 P0/P1 FR/AC"),
        ("contract", "契约、迁移与回滚已定义"),
        ("testability", "A3 可执行，测试命令明确"),
    ),
    "h3": (
        ("candidate", "candidate tag/digest 与各仓 head 一致"),
        ("verdicts", "A4/A5 通过，无未关闭 S0–S2"),
        ("ci", "CI 全绿且 head 一致"),
    ),
}
GATE_ORDER = ("h1", "h2", "h3")
GATE_STATUS = ("pending", "approved", "rejected")
CHECK_RESULTS = ("pass", "fail", "n/a")
H3_SAMPLE_RATE = 0.1
HUMAN_WIP_LIMIT = 2
HUMAN_SLA_HOURS = 24.0


def canonical_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def digest_facts(manifest: dict) -> dict:
    """The immutable facts a candidate digest is rebuilt from.

    Deliberately excludes approvals, metrics, CI state and freeze metadata:
    those are observations about a candidate, not part of its identity.
    """
    docs = manifest.get("docs") or {}
    doc_facts = {}
    for key in DIGEST_DOC_KEYS:
        entry = docs.get(key)
        if isinstance(entry, dict):
            doc_facts[key] = {
                "version": entry.get("version"),
                "sha": entry.get("sha"),
            }
    repos = [
        {
            "repo_id": r.get("repo_id"),
            "base": r.get("base"),
            "branch": r.get("branch"),
            "head": r.get("head"),
        }
        for r in sorted(
            (manifest.get("repos") or []),
            key=lambda r: (str(r.get("merge_order", "")), str(r.get("repo_id", ""))),
        )
        if isinstance(r, dict)
    ]
    return {
        "change_set_id": manifest.get("change_set_id"),
        "issue": manifest.get("issue"),
        "slug": manifest.get("slug"),
        "docs": doc_facts,
        "repos": repos,
    }


def candidate_digest(manifest: dict) -> str:
    return sha256_bytes(canonical_json(digest_facts(manifest)).encode("utf-8"))[:12]


def candidate_tag(manifest: dict, digest: str | None = None) -> str:
    issue = str(manifest.get("issue") or manifest.get("change_set_id") or "").strip()
    return f"candidate/{issue}-{digest or candidate_digest(manifest)}"


def load_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_manifest(path: Path) -> dict:
    data = load_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: manifest root must be an object")
    return data


def iter_manifests(root: Path) -> list[Path]:
    """Accept a manifest file or a directory tree; ignore non-manifest JSON."""
    root = Path(root)
    if root.is_file():
        return [root]
    return sorted(root.rglob(MANIFEST_NAME))


def parse_time(value) -> datetime | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_cmd(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(args, text=True, capture_output=True, cwd=str(cwd) if cwd else None)


def git_head(repo: Path) -> str:
    proc = run_cmd(["git", "-C", str(repo), "rev-parse", "HEAD"])
    if proc.returncode != 0:
        raise RuntimeError(f"git rev-parse failed in {repo}: {proc.stderr.strip()}")
    return proc.stdout.strip()


def normalize_number(value) -> float | int | None:
    """Return a non-negative number or None when the value is malformed."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value < 0:
        return None
    return value
