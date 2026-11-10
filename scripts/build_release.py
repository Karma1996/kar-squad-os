#!/usr/bin/env python3
"""Validate specs and build the migration release package."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RELEASE_DIR = ROOT / "release"
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store", "backups")


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check() -> int:
    errors: list[str] = []
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    bootstrap = load(ROOT / "bootstrap.json")
    if bootstrap.get("version") != version:
        errors.append(f"bootstrap.json version {bootstrap.get('version')} != VERSION {version}")
    if bootstrap.get("config") != "config/KAR-Squad-Config-v4.3.md":
        errors.append("bootstrap.json config path is not v4.3")
    if not (ROOT / "config/KAR-Squad-Config-v4.3.md").exists():
        errors.append("missing config/KAR-Squad-Config-v4.3.md")
    profile = load(ROOT / "skills/kar-squad-profile/squad.json")
    if profile.get("version") != version:
        errors.append(f"kar-squad-profile version {profile.get('version')} != VERSION {version}")
    for name in (
        "docs/GATES.md",
        "docs/MANIFEST.md",
        "docs/METRICS.md",
        "docs/HUMAN-WIP.md",
        "docs/BACKUP-RESTORE.md",
        "docs/ARTIFACTS.md",
        "docs/SECURITY-OVERLAY.md",
        "docs/CHECKPOINT-STEER.md",
        "docs/LEAD-TOUCHPOINTS.md",
        "docs/examples/delivery-manifest.json",
    ):
        if not (ROOT / name).exists():
            errors.append(f"missing v4.3 doc: {name}")
    for name in ("restore.py", "manifest.py", "metrics.py", "human_wip.py", "policy.py", "kar_common.py"):
        if not (ROOT / "scripts" / name).exists():
            errors.append(f"missing script: {name}")

    skills = load(ROOT / "skills.json")
    skill_names = [s["name"] for s in skills]
    if len(skill_names) != len(set(skill_names)):
        errors.append("duplicate skill names")
    for s in skills:
        if not (ROOT / s["path"]).exists():
            errors.append(f"missing skill content: {s['name']}")
        for f in s.get("files", []) or []:
            if not (ROOT / f["source"]).exists():
                errors.append(f"missing skill file: {s['name']}/{f['path']}")

    agents = load(ROOT / "agents.json")
    agent_names = [a["name"] for a in agents]
    if len(agent_names) != len(set(agent_names)):
        errors.append("duplicate agent names")
    for a in agents:
        if not (ROOT / "agents" / f"{a['name']}.md").exists():
            errors.append(f"missing agent instructions: {a['name']}")
        if not (1 <= int(a["max"]) <= 50):
            errors.append(f"invalid concurrency for {a['name']}: {a['max']}")
        for bound in a["skills"]:
            if bound not in skill_names:
                errors.append(f"agent {a['name']} binds unknown skill {bound}")
        for required in ("kar-squad-profile", "kar-doc-template"):
            if required not in a["skills"]:
                errors.append(f"agent {a['name']} missing {required}")

    squad = load(ROOT / "squad/KAR-Delivery-Squad.json")
    if squad.get("leader") not in agent_names:
        errors.append("squad leader is not an agent in agents.json")
    for m in squad.get("members", []):
        if m["name"] not in agent_names:
            errors.append(f"squad member not in agents.json: {m['name']}")

    tpl_dir = ROOT / "skills/kar-doc-template/templates"
    html = tpl_dir / "KAR-Deliverable-Template.html"
    meta = tpl_dir / "template.json"
    if not html.exists() or not meta.exists():
        errors.append("missing template HTML or template.json")
    else:
        info = load(meta)
        if info.get("version") != "4.1":
            errors.append(f"template version is {info.get('version')}, expected 4.1")
        if info.get("sha256") != sha256(html):
            errors.append("template.json sha256 does not match HTML")
        if not info.get("slots"):
            errors.append("template.json has no slots")
        if 'data-template-version="4.1"' not in html.read_text(encoding="utf-8"):
            errors.append("template HTML does not declare data-template-version=4.1")

    if errors:
        print("CHECK: FAIL")
        for e in errors:
            print("  ERROR:", e)
        return 1
    print(f"CHECK: OK  version={version}  skills={len(skills)}  agents={len(agents)}")
    return 0


def build() -> int:
    rc = check()
    if rc:
        return rc
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    name = f"KAR-Squad-Bootstrap-v{version}"
    target = RELEASE_DIR / name
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)

    files = [
        "README.md",
        "VERSION",
        "CHANGELOG.md",
        "bootstrap.json",
        "agents.json",
        "skills.json",
        "config",
        "agents",
        "skills",
        "squad",
        "CONTRIBUTING.md",
        "docs",
    ]
    for item in files:
        src = ROOT / item
        dst = target / item
        if src.is_dir():
            shutil.copytree(src, dst, ignore=IGNORE)
        elif src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        else:
            print(f"WARN: missing release item: {item}")
    for script in ("bootstrap.py", "verify.py", "restore.py", "manifest.py", "metrics.py", "human_wip.py", "policy.py", "kar_common.py"):
        src = ROOT / "scripts" / script
        dst = target / "scripts" / script
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    entries = []
    for p in sorted(target.rglob("*")):
        if p.is_file():
            entries.append({
                "path": p.relative_to(target).as_posix(),
                "sha256": sha256(p),
                "bytes": p.stat().st_size,
            })
    manifest = {
        "name": "KAR Delivery Squad Bootstrap Kit",
        "version": version,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "file_count": len(entries),
        "files": entries,
    }
    (target / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (target / "SHA256SUMS").write_text(
        "\n".join(f"{e['sha256']}  {e['path']}" for e in entries) + "\n", encoding="utf-8"
    )
    zip_path = RELEASE_DIR / f"{name}.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(target.rglob("*")):
            if p.is_file():
                zf.write(p, p.relative_to(RELEASE_DIR).as_posix())
    print(f"BUILT {zip_path}  files={len(entries)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Check specs or build the KAR Squad OS release")
    ap.add_argument("--check", action="store_true", help="Validate specs/template/version only")
    args = ap.parse_args()
    return check() if args.check else build()


if __name__ == "__main__":
    sys.exit(main())
