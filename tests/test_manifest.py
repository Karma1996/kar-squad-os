#!/usr/bin/env python3
import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts/manifest.py"
sys.path.insert(0, str(ROOT / "scripts"))
from kar_common import GATE_CHECKS, candidate_digest, candidate_tag  # noqa: E402


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def git(repo, *args):
    proc = subprocess.run(["git", "-C", str(repo), *args], text=True, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr)
    return proc.stdout.strip()


def make_repo(root):
    repo = root / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Test")
    git(repo, "checkout", "-q", "-b", "feat/KAR-11-candidate")
    (repo / "app.txt").write_text("one\n")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "init")
    return repo, git(repo, "rev-parse", "HEAD")


def make_docs(root):
    docs = root / "docs"
    docs.mkdir()
    entries = {}
    for key in ("requirements", "design", "test_design", "dev_notes", "qa_report", "prototype"):
        text = f"<html>{key}</html>"
        path = docs / f"{key}.html"
        path.write_text(text, encoding="utf-8")
        entry = {"path": path.name, "version": "1.0", "sha": sha(text)}
        if key == "prototype":
            entry.update({"mode": "B", "approved_by": "user-1", "approved_at": "2026-11-01T00:00:00Z"})
        entries[key] = entry
    return docs, entries


def make_manifest(root):
    repo, head = make_repo(root)
    docs, entries = make_docs(root)
    manifest = {
        "version": 2,
        "change_set_id": "KAR-11",
        "issue": "KAR-11",
        "slug": "candidate-freeze",
        "risk": "R2",
        "decision_owner": "user-1",
        "docs": entries,
        "repos": [{
            "repo_id": "app",
            "remote": str(repo),
            "base": "main",
            "branch": "feat/KAR-11-candidate",
            "head": head,
            "pr": "https://github.com/example/app/pull/12",
            "merge_order": 1,
            "ci": {
                "status": "passed",
                "head": head,
                "url": "https://github.com/example/app/actions/runs/1",
                "checked_at": "2026-11-01T00:00:00Z",
            },
        }],
    }
    path = root / "delivery-manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return path, repo, docs, head


def run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], text=True, capture_output=True)


def gate(key, *, digest=None):
    checks = [
        {"id": check_id, "result": "pass", "evidence": f"evidence/{check_id}.log"}
        for check_id, _ in GATE_CHECKS[key]
    ]
    data = {
        "status": "approved",
        "requested_at": "2026-11-01T00:00:00Z",
        "approved_by": "user-1",
        "approver_type": "human",
        "approved_at": "2026-11-01T01:00:00Z",
        "rationale": "范围、证据与候选一致，可以进入下一道门。",
        "conditions": [],
        "checks": checks,
    }
    if key == "h3":
        data["candidate_digest"] = digest
        data["sampling"] = {
            "rate": 0.1,
            "population": 3,
            "sampled": ["h1"],
            "reviewed_by": "user-2",
            "at": "2026-11-02T00:00:00Z",
            "note": "抽样复核 h1 检查项与批准记录一致，无发现。",
        }
    return data


class ManifestFreezeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.path, self.repo, self.docs, self.head = make_manifest(self.root)
        self.base = ["--manifest", str(self.path), "--docs-root", str(self.docs), "--repo-root", f"app={self.repo}"]

    def tearDown(self):
        self.tmp.cleanup()

    def test_freeze_writes_rebuildable_candidate_tag(self):
        data = json.loads(self.path.read_text())
        rebuilt = candidate_digest(data)
        proc = run("freeze", *self.base, "--write")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        data = json.loads(self.path.read_text())
        self.assertEqual(data["candidate"]["digest"], rebuilt)
        self.assertEqual(data["candidate"]["tag"], f"candidate/KAR-11-{rebuilt}")
        self.assertTrue(data["candidate"]["frozen_at"])
        proc = run("check", *self.base, "--profile", "freeze", "--check-remotes")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("tag: candidate/KAR-11-", proc.stdout)

    def test_late_push_invalidates_candidate(self):
        self.assertEqual(run("freeze", *self.base, "--write").returncode, 0)
        (self.repo / "late.txt").write_text("late\n")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-q", "-m", "late push")
        proc = run("check", *self.base, "--profile", "freeze")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("LATE PUSH", proc.stdout)

    def test_doc_change_invalidates_candidate(self):
        self.assertEqual(run("freeze", *self.base, "--write").returncode, 0)
        (self.docs / "requirements.html").write_text("<html>changed</html>")
        proc = run("check", *self.base, "--profile", "freeze")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("sha mismatch", proc.stdout)

    def test_refreeze_after_input_change_succeeds(self):
        self.assertEqual(run("freeze", *self.base, "--write").returncode, 0)
        old_digest = json.loads(self.path.read_text())["candidate"]["digest"]
        changed = "<html>requirements v2</html>"
        (self.docs / "requirements.html").write_text(changed)
        data = json.loads(self.path.read_text())
        data["docs"]["requirements"]["sha"] = sha(changed)
        self.path.write_text(json.dumps(data), encoding="utf-8")
        proc = run("freeze", *self.base, "--write")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        new_digest = json.loads(self.path.read_text())["candidate"]["digest"]
        self.assertNotEqual(old_digest, new_digest)
        self.assertEqual(run("check", *self.base, "--profile", "freeze").returncode, 0)

    def test_tampered_digest_fails(self):
        self.assertEqual(run("freeze", *self.base, "--write").returncode, 0)
        data = json.loads(self.path.read_text())
        data["candidate"]["digest"] = "000000000000"
        self.path.write_text(json.dumps(data), encoding="utf-8")
        proc = run("check", *self.base, "--profile", "freeze")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("STALE", proc.stdout)

    def test_draft_does_not_require_files(self):
        (self.docs / "requirements.html").unlink()
        proc = run("check", *self.base, "--profile", "draft")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


class ManifestH3Test(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.path, self.repo, self.docs, self.head = make_manifest(self.root)
        self.base = ["--manifest", str(self.path), "--docs-root", str(self.docs), "--repo-root", f"app={self.repo}"]
        self.assertEqual(run("freeze", *self.base, "--write").returncode, 0)
        self.manifest = json.loads(self.path.read_text())
        digest = self.manifest["candidate"]["digest"]
        self.manifest["gates"] = {key: gate(key, digest=digest) for key in ("h1", "h2", "h3")}
        self.manifest["metrics"] = {
            "human_touches": 3,
            "wait_human": 5.5,
            "rework_rounds": 1,
            "candidate_recuts": 2,
            "escaped_defects": 0,
            "cycle_time_hours": 30,
        }
        self.manifest["lane"] = "standard"
        self.manifest["artifacts"] = [
            {"kind": "requirements", "ref": "requirements.html"},
            {"kind": "design", "ref": "design.html"},
            {"kind": "test_design", "ref": "test_design.html"},
        ]
        self.manifest["checkpoints"] = {
            "h1_draft": {
                "published_at": "2026-10-31T23:30:00Z",
                "review_window_minutes": 10,
                "reviewers": ["user-1"],
                "outcome": "unchanged",
                "steer_ids": [],
            },
            "h2_draft": {
                "published_at": "2026-10-31T23:40:00Z",
                "review_window_minutes": 10,
                "reviewers": ["user-1"],
                "outcome": "unchanged",
                "steer_ids": [],
            },
        }
        self.manifest["steers"] = []
        self.manifest["touchpoints"] = [
            {"kind": "intake", "at": "2026-10-31T23:00:00Z", "actor": "user-1"},
            {"kind": "contract", "at": "2026-10-31T23:15:00Z", "actor": "user-1"},
            {"kind": "gates", "gate": "h1", "at": "2026-11-01T00:00:00Z", "actor": "user-1"},
            {"kind": "gates", "gate": "h2", "at": "2026-11-01T00:00:00Z", "actor": "user-1"},
            {"kind": "gates", "gate": "h3", "at": "2026-11-01T00:00:00Z", "actor": "user-1"},
        ]
        self.write(self.manifest)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, data):
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def check(self, data):
        self.write(data)
        return run("check", *self.base, "--profile", "h3")

    def test_full_h3_manifest_passes(self):
        proc = self.check(self.manifest)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_missing_gate_check_fails(self):
        data = copy.deepcopy(self.manifest)
        data["gates"]["h2"]["checks"].pop()
        proc = self.check(data)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("exactly 3 checks", proc.stdout)

    def test_missing_rationale_fails(self):
        data = copy.deepcopy(self.manifest)
        data["gates"]["h1"]["rationale"] = ""
        proc = self.check(data)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("rationale", proc.stdout)

    def test_agent_approval_fails(self):
        data = copy.deepcopy(self.manifest)
        data["gates"]["h1"]["approver_type"] = "agent"
        proc = self.check(data)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("must be human", proc.stdout)

    def test_r3_requires_second_reviewer_and_security_overlay(self):
        data = copy.deepcopy(self.manifest)
        data["risk"] = "R3"
        proc = self.check(data)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("second_reviewer", proc.stdout)
        self.assertIn("security_overlay", proc.stdout)
        data["gates"]["h3"]["second_reviewer"] = {
            "reviewer": "user-3",
            "role": "security",
            "verdict": "pass",
            "at": "2026-11-02T02:00:00Z",
        }
        data["artifacts"] = [
            {"kind": "requirements", "ref": "requirements.html"},
            {"kind": "prototype", "ref": "prototype.html"},
            {"kind": "design", "ref": "design.html"},
            {"kind": "test_design", "ref": "test_design.html"},
            {"kind": "dev_notes", "ref": "dev_notes.html"},
            {"kind": "qa_report", "ref": "qa_report.html"},
            {"kind": "security_overlay", "ref": "threat-model.html"},
        ]
        data["security_overlay"] = {
            "threat_model": {"path": "threat-model.html", "version": "1.0", "sha": "a" * 64},
            "permission_matrix": {"path": "permissions.html", "version": "1.0", "sha": "b" * 64},
            "secret_scan": {"tool": "gitleaks", "status": "passed", "findings": 0, "at": "2026-11-01T00:00:00Z"},
            "dependency_scan": {"tool": "osv-scanner", "status": "passed", "findings": 0, "at": "2026-11-01T00:00:00Z"},
            "rollback_drill": {"at": "2026-11-01T00:00:00Z", "result": "passed", "evidence": "evidence/drill.md"},
            "reviewer": {
                "id": "user-3",
                "role": "security",
                "independent": True,
                "verdict": "pass",
                "at": "2026-11-01T00:30:00Z",
                "scope": "authz, secrets, rollback",
            },
        }
        proc = self.check(data)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_h3_sampling_required(self):
        data = copy.deepcopy(self.manifest)
        del data["gates"]["h3"]["sampling"]
        proc = self.check(data)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("sampling", proc.stdout)

    def test_pending_gate_fails_h3(self):
        data = copy.deepcopy(self.manifest)
        data["gates"]["h2"]["status"] = "pending"
        del data["gates"]["h2"]["approved_at"]
        data["gates"]["h2"]["requested_at"] = "2026-11-04T02:00:00Z"
        proc = self.check(data)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("must be approved at H3", proc.stdout)

    def test_metrics_required(self):
        data = copy.deepcopy(self.manifest)
        del data["metrics"]
        proc = self.check(data)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("metrics", proc.stdout)


class ManifestExternalTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.path, self.repo, self.docs, self.head = make_manifest(self.root)
        self.assertEqual(
            run("freeze", "--manifest", str(self.path), "--docs-root", str(self.docs),
                "--repo-root", f"app={self.repo}", "--write").returncode,
            0,
        )
        self.base = ["--manifest", str(self.path), "--docs-root", str(self.docs), "--repo-root", f"app={self.repo}"]

    def tearDown(self):
        self.tmp.cleanup()

    def fake_gh(self, bucket="pass", state="OPEN"):
        script = self.root / "gh"
        script.write_text(
            "#!/usr/bin/env python3\n"
            "import json, sys\n"
            "args = sys.argv[1:]\n"
            f"head = {self.head!r}\n"
            "if 'checks' in args:\n"
            f"    print(json.dumps([{{'name': 'ci', 'state': 'SUCCESS', 'bucket': {bucket!r}, 'link': 'x'}}]))\n"
            "elif 'view' in args:\n"
            f"    print(json.dumps({{'headRefOid': head, 'state': {state!r}, 'url': 'x'}}))\n"
            "else:\n"
            "    print('{}')\n",
            encoding="utf-8",
        )
        os.chmod(script, 0o755)
        return script

    def test_external_pr_and_ci_pass(self):
        gh = self.fake_gh()
        proc = run("check", *self.base, "--profile", "freeze", "--check-prs", "--check-ci", "--gh", str(gh))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_external_ci_failure_fails(self):
        gh = self.fake_gh(bucket="fail")
        proc = run("check", *self.base, "--profile", "freeze", "--check-ci", "--gh", str(gh))
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("CI not green", proc.stdout)

    def test_external_pr_head_mismatch_fails(self):
        gh = self.fake_gh()
        data = json.loads(self.path.read_text())
        data["repos"][0]["ci"]["head"] = "0" * 40
        self.path.write_text(json.dumps(data), encoding="utf-8")
        proc = run("check", *self.base, "--profile", "freeze", "--check-ci", "--check-prs", "--gh", str(gh))
        self.assertNotEqual(proc.returncode, 0)


if __name__ == "__main__":
    unittest.main()
