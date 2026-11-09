#!/usr/bin/env python3
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


class SpecsTest(unittest.TestCase):
    def setUp(self):
        self.skills = load("skills.json")
        self.agents = load("agents.json")
        self.squad = load("squad/KAR-Delivery-Squad.json")
        self.bootstrap = load("bootstrap.json")
        self.version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()

    def test_versions_match(self):
        self.assertEqual(self.bootstrap["version"], self.version)
        self.assertEqual(self.bootstrap["config"], "config/KAR-Squad-Config-v4.1.md")

    def test_skill_files_exist(self):
        names = set()
        for s in self.skills:
            self.assertNotIn(s["name"], names)
            names.add(s["name"])
            self.assertTrue((ROOT / s["path"]).exists(), s["name"])
            for f in s.get("files", []) or []:
                self.assertTrue((ROOT / f["source"]).exists(), f"{s['name']}/{f['path']}")

    def test_agents_have_profile_and_template(self):
        skill_names = {s["name"] for s in self.skills}
        for a in self.agents:
            self.assertTrue((ROOT / "agents" / f"{a['name']}.md").exists())
            self.assertIn("kar-squad-profile", a["skills"])
            self.assertIn("kar-doc-template", a["skills"])
            for bound in a["skills"]:
                self.assertIn(bound, skill_names)
            self.assertGreaterEqual(a["max"], 1)
            self.assertLessEqual(a["max"], 50)

    def test_squad_members(self):
        agent_names = {a["name"] for a in self.agents}
        self.assertIn(self.squad["leader"], agent_names)
        for m in self.squad["members"]:
            self.assertIn(m["name"], agent_names)

    def test_config_doc_mentions_v41(self):
        doc = (ROOT / "config/KAR-Squad-Config-v4.1.md").read_text(encoding="utf-8")
        for needle in ("v4.1", "kar-squad-profile", "kar-doc-template", "squad-overlay"):
            self.assertIn(needle, doc)


if __name__ == "__main__":
    unittest.main()
