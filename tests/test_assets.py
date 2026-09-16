import hashlib
from pathlib import Path
import re
import unittest
from urllib.parse import unquote, urlsplit

from harness_factory import load_json, validate
from harness_factory.contracts import relative_path
from harness_factory.skill_bundle import validate_skill_bundle


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_LICENSE_NOTICE_SHA256 = {
    "licenses/gstack.txt": "e56fbb5b3d95756f3fa1cfefa24732ec79f18ece1ad08a4e79e00df57e8b198c",
    "licenses/mattpocock.txt": "0e7ac423bf2c6e223b7c5b156f8cf72da49d748e56a1641402c31f22ad07dbb5",
    "licenses/superpowers.txt": "a37e0e9697144819e1d965176ac4ae5bc3fa02d11e7812036bbcadf6dafe2400",
}


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
                    self.assertTrue(
                        {"schema_version", "runtime", "bundles", "cases"} <= set(report)
                    )
                    self.assertEqual(report["schema_version"], 2)
                    self.assertEqual(report["runtime"], "copilot-cli")
                    self.assertTrue(report["cases"])
                    self.assertTrue(all(case["pass"] is True for case in report["cases"]))
                    bundle = validate_skill_bundle(
                        self.catalog_root / row["path"], row["id"]
                    )
                    self.assertEqual(report["bundles"][row["id"]], bundle["digest"])

    def test_actual_evidence_covers_required_behavior_classes(self):
        report = load_json(self.catalog_root / "evidence/copilot-behavior.json")
        required = {
            "success",
            "ambiguous-input",
            "approval-refusal",
            "missing-access",
            "failed-check",
            "resume",
            "uncertain-write",
            "instruction-injection",
        }
        self.assertTrue(required.issubset(set(report["behavior_classes"])))
        for skill in self.catalog["skills"]:
            bundle = validate_skill_bundle(
                self.catalog_root / skill["path"], skill["id"]
            )
            self.assertEqual(report["bundles"][skill["id"]], bundle["digest"])

    def test_curated_reference_index_is_pinned_hashed_and_reviewed(self):
        index = load_json(ROOT / "catalog/references/index.json")
        self.assertEqual(set(index), {"schema_version", "references"})
        self.assertEqual(index["schema_version"], 1)
        expected_sources = {
            (row["source"]["url"], row["source"]["revision"], row["source"]["path"])
            for row in self.catalog["skills"]
        }
        self.assertEqual(len(index["references"]), len(expected_sources))
        self.assertEqual(
            {
                (
                    reference["source"]["url"],
                    reference["source"]["revision"],
                    reference["source"]["path"],
                )
                for reference in index["references"]
            },
            expected_sources,
        )
        self.assertEqual(
            len({reference["id"] for reference in index["references"]}),
            len(index["references"]),
        )
        for reference in index["references"]:
            self.assertEqual(set(reference), {
                "id", "capabilities", "source", "snapshot", "sha256",
                "license_file", "adopt", "exclude", "review_status",
            })
            self.assertEqual(
                set(reference["source"]), {"url", "revision", "path", "license"}
            )
            for field in ("capabilities", "adopt", "exclude"):
                self.assertIsInstance(reference[field], list)
                self.assertTrue(reference[field])
                self.assertTrue(all(isinstance(value, str) and value for value in reference[field]))
            self.assertRegex(reference["source"]["revision"], r"^[a-f0-9]{40}$")
            reference_root = ROOT / "catalog/references"
            path = relative_path(reference_root, reference["snapshot"], "snapshot")
            self.assertEqual(reference["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertEqual(reference["source"]["license"], "MIT")
            license_path = relative_path(
                reference_root, reference["license_file"], "license_file"
            )
            expected_license_sha256 = EXPECTED_LICENSE_NOTICE_SHA256[reference["license_file"]]
            license_bytes = license_path.read_bytes()
            self.assertEqual(
                hashlib.sha256(license_bytes).hexdigest(),
                expected_license_sha256,
            )
            license_text = license_bytes.decode("utf-8")
            self.assertIn("Permission is hereby granted", license_text)
            self.assertIn("THE SOFTWARE IS PROVIDED", license_text)
            self.assertEqual(reference["review_status"], "reviewed")
            self.assertTrue(reference["adopt"])
            self.assertTrue(reference["exclude"])

    def test_curated_reference_license_notice_digest_pins_detect_byte_changes(self):
        reference_root = ROOT / "catalog/references"
        for license_file, expected_sha256 in EXPECTED_LICENSE_NOTICE_SHA256.items():
            with self.subTest(license_file=license_file):
                path = relative_path(reference_root, license_file, "license_file")
                self.assertNotEqual(
                    hashlib.sha256(path.read_bytes() + b"\n").hexdigest(),
                    expected_sha256,
                )

    def test_curated_reference_library_contains_only_non_executable_assets(self):
        reference_root = ROOT / "catalog/references"
        index = load_json(reference_root / "index.json")
        expected = {reference_root / "index.json"}
        for reference in index["references"]:
            expected.add(relative_path(reference_root, reference["snapshot"], "snapshot"))
            expected.add(relative_path(reference_root, reference["license_file"], "license_file"))
        actual = {path for path in reference_root.rglob("*") if path.is_file()}
        self.assertEqual(actual, expected)
        for path in actual:
            with self.subTest(path=path):
                self.assertIn(path.suffix, {".json", ".md", ".txt"})
                self.assertEqual(path.stat().st_mode & 0o111, 0)

    def test_actual_skills_have_progressive_disclosure_resources(self):
        required = {
            "hf-clarify": ["references/decision-tree.md", "templates/brief.md"],
            "hf-plan": ["references/task-sizing.md", "templates/plan.md"],
            "hf-tdd": [
                "references/failure-classification.md",
                "templates/test-results.md",
            ],
            "hf-review": ["references/checklist.md", "templates/review-report.md"],
            "hf-manual": ["references/uncertain-writes.md", "templates/handoff.md"],
            "hf-issues-markdown": [
                "references/update-rules.md",
                "templates/issue.md",
            ],
        }
        for skill_id, resources in required.items():
            root = self.catalog_root / "skills" / skill_id
            entry = (root / "SKILL.md").read_text(encoding="utf-8")
            for resource in resources:
                self.assertTrue((root / resource).is_file())
                self.assertIn(resource, entry)
            validate_skill_bundle(root, skill_id)

    def test_manual_checks_uncertain_write_before_normal_handoff(self):
        text = (
            self.catalog_root / "skills/hf-manual/SKILL.md"
        ).read_text(encoding="utf-8")
        uncertain_branch = "Check for an earlier uncertain write"
        normal_branch = "If no prior write is uncertain"
        self.assertIn(uncertain_branch, text)
        self.assertIn(normal_branch, text)
        self.assertLess(text.index(uncertain_branch), text.index(normal_branch))

    def test_clarify_disambiguates_operation_before_owner_or_timing(self):
        skill = (
            self.catalog_root / "skills/hf-clarify/SKILL.md"
        ).read_text(encoding="utf-8")
        reference = (
            self.catalog_root / "skills/hf-clarify/references/decision-tree.md"
        ).read_text(encoding="utf-8")
        normalized_skill = " ".join(skill.split())

        sequencing_rule = "must disambiguate the target operation before ownership"
        blocker_rule = "immediate prerequisite for the current frontier decision"
        self.assertIn(sequencing_rule, normalized_skill)
        self.assertIn(blocker_rule, normalized_skill)
        self.assertIn("operation disambiguation is upstream", reference)

    def test_plan_supports_validation_only_tasks(self):
        paths = [
            "skills/hf-plan/SKILL.md",
            "skills/hf-plan/references/task-sizing.md",
            "skills/hf-plan/templates/plan.md",
        ]
        for path in paths:
            with self.subTest(path=path):
                text = (self.catalog_root / path).read_text(encoding="utf-8")
                self.assertIn("validation-only", text)

    def test_validation_only_plan_executes_without_a_red_green_cycle(self):
        plan = (
            self.catalog_root / "skills/hf-plan/SKILL.md"
        ).read_text(encoding="utf-8")
        executor = (
            self.catalog_root / "skills/hf-tdd/SKILL.md"
        ).read_text(encoding="utf-8")
        results = (
            self.catalog_root / "skills/hf-tdd/templates/test-results.md"
        ).read_text(encoding="utf-8")
        normalized_plan = " ".join(plan.split())
        normalized_executor = " ".join(executor.split())

        self.assertIn(
            "either `test-first` or `validation-only`", normalized_plan
        )
        self.assertIn("exact validation command", normalized_plan)
        self.assertIn("observed validation evidence", normalized_plan)
        validation_branch = "For an approved `validation-only` task"
        test_first_branch = "Write one focused test"
        self.assertIn(validation_branch, normalized_executor)
        self.assertIn(test_first_branch, normalized_executor)
        self.assertLess(
            normalized_executor.index(validation_branch),
            normalized_executor.index(test_first_branch),
        )
        self.assertIn("smallest local change", normalized_executor)
        self.assertIn("exact validation command", normalized_executor)
        self.assertIn("observed validation evidence", normalized_executor)
        self.assertIn("no red/green cycle applies", normalized_executor)
        self.assertIn(
            "use validation-only to bypass TDD for code or bug fixes",
            normalized_executor,
        )
        self.assertIn("Only after valid red", normalized_executor)
        self.assertIn("## Validation-only tasks", results)
        self.assertIn("Red/green cycle: `not-applicable`", results)

    def test_plan_distinguishes_existing_surfaces_from_approved_proposed_paths(self):
        text = (
            self.catalog_root / "skills/hf-plan/references/task-sizing.md"
        ).read_text(encoding="utf-8")
        self.assertIn("Observed existing surfaces", text)
        self.assertIn("Approved proposed paths", text)

    def test_plan_template_never_labels_proposed_paths_as_verified(self):
        text = (
            self.catalog_root / "skills/hf-plan/templates/plan.md"
        ).read_text(encoding="utf-8")
        self.assertIn("## Observed existing surfaces", text)
        self.assertIn("## Brief-authorized proposed paths", text)
        self.assertNotIn("## Project surfaces", text)
        self.assertNotIn("<verified surface IDs>", text)
        proposed_paths = text.split("## Brief-authorized proposed paths", 1)[1]
        proposed_paths = proposed_paths.split("## Tasks", 1)[0]
        self.assertNotIn("verified", proposed_paths.lower())

    def test_markdown_issue_skill_has_read_only_branch_and_evidence(self):
        text = (
            self.catalog_root / "skills/hf-issues-markdown/SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("For a read-only request", text)
        self.assertIn("`changed: false`", text)

    def test_markdown_issue_updates_require_atomic_conflict_guards(self):
        text = (
            self.catalog_root / "skills/hf-issues-markdown/references/update-rules.md"
        ).read_text(encoding="utf-8")
        self.assertIn("no-clobber", text)
        self.assertIn("conditional replacement", text)
        self.assertIn(
            "block the write when either guarantee is unavailable", text.lower()
        )

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
