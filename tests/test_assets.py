from pathlib import Path
import re
import hashlib
import unittest
from urllib.parse import unquote, urlsplit

from harness_factory import load_json, validate
from harness_factory.contracts import relative_path


ROOT = Path(__file__).resolve().parents[1]


class AssetTests(unittest.TestCase):
    def setUp(self):
        self.catalog_root = ROOT / "catalog"
        self.catalog = load_json(self.catalog_root / "catalog.json")

    def test_actual_skills_have_matching_frontmatter_and_valid_local_links(self):
        skills = [(row["id"], self.catalog_root / row["path"] / "SKILL.md")
                  for row in self.catalog["skills"]]
        skills.append(("harness-factory", ROOT / ".agents/skills/harness-factory/SKILL.md"))
        for name, path in skills:
            with self.subTest(skill=name):
                text = path.read_text(encoding="utf-8")
                self.assertTrue(text.startswith("---\n"))
                frontmatter, separator, body = text[4:].partition("\n---\n")
                self.assertTrue(separator)
                fields = dict(re.findall(r"^([a-z-]+):[ \t]*(.+)$", frontmatter, re.MULTILINE))
                self.assertEqual(fields["name"].strip("\"'"), name)
                self.assertTrue(fields["description"].strip("\"'"))
                self.assertTrue(body.strip())
        markdown_files = list((self.catalog_root / "skills").rglob("*.md"))
        markdown_files += list((ROOT / ".agents/skills/harness-factory").rglob("*.md"))
        for path in markdown_files:
            for link in re.findall(r"\[[^\]]*\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
                url = urlsplit(link)
                if url.scheme or url.netloc or not url.path:
                    continue
                target = (path.parent / unquote(url.path)).resolve()
                with self.subTest(source=path, link=link):
                    self.assertIn(ROOT, target.parents)
                    self.assertTrue(target.is_file(), "broken local markdown reference: " + link)

    def test_actual_provenance_pins_and_mit_notices_exist(self):
        self.assertEqual(set(self.catalog), {"schema_version", "skills"})
        for row in self.catalog["skills"]:
            with self.subTest(skill=row["id"]):
                source = row["source"]
                self.assertRegex(source["revision"], r"^[a-f0-9]{40}$")
                self.assertTrue(source["url"].startswith("https://github.com/"))
                self.assertEqual(source["license"], "MIT")
                license_path = relative_path(self.catalog_root, source["license_file"], "license_file")
                license_text = license_path.read_text(encoding="utf-8")
                self.assertIn("Copyright", license_text)
                self.assertIn("Permission is hereby granted", license_text)
                self.assertIn("THE SOFTWARE IS PROVIDED", license_text)
                relative_path(self.catalog_root, row["path"], "skill.path", directory=True)
                if row["compatibility"]["status"] == "verified":
                    evidence = relative_path(self.catalog_root, row["compatibility"]["evidence"], "evidence")
                    report = load_json(evidence)
                    self.assertEqual(report["schema_version"], 1)
                    self.assertEqual(report["runtime"], "copilot-cli")
                    self.assertTrue(report["cases"])
                    self.assertTrue(all(case["pass"] is True for case in report["cases"]))
                    self.assertEqual(report["skills"][row["id"]],
                                     hashlib.sha256((self.catalog_root / row["path"] / "SKILL.md").read_bytes()).hexdigest())

    def test_example_validates_when_selected_behavior_evidence_is_verified(self):
        profile = load_json(ROOT / "examples/github-issue/profile.json")
        workflow = load_json(ROOT / "examples/github-issue/workflow.json")
        selected = {step["skill"] for step in workflow["steps"]}
        if any(row["compatibility"]["status"] != "verified"
               for row in self.catalog["skills"] if row["id"] in selected):
            self.skipTest("Parent behavior evaluation has not verified all selected skills yet.")
        validate(profile, workflow, self.catalog, self.catalog_root)
        self.assertEqual(workflow["outputs"], ["pr-url"])

    def test_markdown_issue_skill_defines_required_format_and_git_boundary(self):
        text = (
            ROOT / "catalog/skills/hf-issues-markdown/SKILL.md"
        ).read_text(encoding="utf-8")
        for required in [
            "id:",
            "title:",
            "status:",
            "owners:",
            "labels:",
            "created:",
            "updated:",
            "## Summary",
            "## Acceptance criteria",
            "## Context",
            "## Work log",
            "open",
            "in-progress",
            "blocked",
            "review",
            "done",
            "cancelled",
            "Do not commit or push",
        ]:
            with self.subTest(required=required):
                self.assertIn(required, text)
