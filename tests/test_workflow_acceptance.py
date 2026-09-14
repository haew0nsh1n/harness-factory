import json
import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from harness_factory import (
    apply_install,
    check_package,
    generate_package,
    load_json,
    plan_install,
    seal_evaluation,
)


ROOT = Path(__file__).resolve().parents[1]


class WorkflowAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(
            prefix="harness-acceptance-", dir=str(ROOT / "tests")
        )
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name).resolve()
        self.package = self.root / "package"
        self.target = self.root / "customer"
        self.target.mkdir()
        (self.target / "README.md").write_text("Customer-owned readme\n")
        self.workflow = load_json(ROOT / "examples/github-issue/workflow.json")
        self.scenarios = load_json(ROOT / "examples/github-issue/scenarios.json")
        generate_package(
            load_json(ROOT / "examples/github-issue/profile.json"),
            self.workflow,
            self.scenarios,
            load_json(ROOT / "catalog/catalog.json"),
            ROOT / "catalog",
            self.package,
        )
        example_results = load_json(ROOT / "examples/github-issue/results.json")
        self.assertEqual(
            example_results["package_manifest_sha256"],
            "<generated-manifest-sha256>",
        )
        example_results["package_manifest_sha256"] = hashlib.sha256(
            (self.package / ".harness/manifest.json").read_bytes()
        ).hexdigest()
        seal_evaluation(self.package, example_results)
        preview = plan_install(self.package, self.target)
        self.assertEqual(preview["operation"], "install-preview")
        self.assertFalse((self.target / ".agents").exists())
        apply_install(self.package, self.target, preview["digest"])

    def cli(self, *args, success=True):
        result = subprocess.run(
            [sys.executable, "-m", "harness_factory", *args],
            cwd=str(self.target),
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(
            result.returncode == 0,
            success,
            msg=result.stdout + result.stderr,
        )
        payload = json.loads(result.stdout if success else result.stderr)
        self.assertEqual(payload["ok"], success)
        return payload

    def record(self, step, status, *extra, success=True, run="demo"):
        return self.cli(
            "record", "--package", ".", "--run", run,
            "--step", step, "--status", status, *extra, success=success
        )

    def test_factory_docs_define_tracker_choices_and_skill_first_fallback(self):
        skill = (
            ROOT / ".agents/skills/harness-factory/SKILL.md"
        ).read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for text in (skill, readme):
            for phrase in ("Git + Markdown", "GitHub Issues", "Jira", "skill", "MCP"):
                with self.subTest(document=text[:20], phrase=phrase):
                    self.assertIn(phrase, text)

        skill_tracker = skill[
            skill.index("Choose and record exactly one issue tracker"):
            skill.index("Read-only environment discovery")
        ]
        readme_tracker = readme[
            readme.index("## 이슈 트래커 선택"):
            readme.index("## 제공하는 기본 스킬")
        ]
        self.assertLess(skill_tracker.index("skill"), skill_tracker.index("MCP"))
        self.assertLess(readme_tracker.index("skill"), readme_tracker.index("MCP"))
        for command in ("tracker-guide", "preflight", "delivery-check"):
            self.assertIn(command, readme_tracker)

        interview = (
            ROOT / ".agents/skills/harness-factory/references/interview.md"
        ).read_text(encoding="utf-8")
        self.assertIn("record exactly one", interview)
        self.assertIn("Never collect credentials", interview)
        self.assertIn("approved MCP", interview)

    def test_installed_runtime_survives_real_customer_edits_and_full_handoff(self):
        subprocess.run(
            ["git", "init", "-q"], cwd=str(self.target), check=True,
            capture_output=True, timeout=10
        )
        (self.target / "README.md").write_text("Customer changed their readme\n")
        source = self.target / "src"
        source.mkdir()
        (source / "feature.py").write_text("def accept(value):\n    return bool(value)\n")
        other_skill = self.target / ".agents/skills/customer-existing"
        other_skill.mkdir()
        (other_skill / "SKILL.md").write_text("Customer-owned skill\n")
        self.cli("check", "--package", ".")
        readiness = self.cli("preflight", "--package", ".")
        self.assertFalse(readiness["ready"])
        self.assertFalse(readiness["read_probes"])
        self.assertEqual(readiness["issue_tracker"]["selected"], "mcp")
        self.assertEqual(readiness["issue_tracker"]["status"], "manual")
        delivery = self.cli("delivery-check", "--package", ".")
        self.assertFalse(delivery["ready"])
        self.assertEqual(delivery["integrity"], {"status": "passed"})
        self.assertEqual(delivery["customer_evaluation"], {"status": "passed"})
        self.assertIn(delivery["environment"]["status"], ("unverified", "blocked"))
        self.assertEqual(delivery["environment"]["assessment"]["operation"], "preflight")
        artifacts = self.target / "docs/work"
        artifacts.mkdir(parents=True)

        for step in self.workflow["steps"]:
            after = step.get("approval_timing", "before") == "after"
            if step["approval"] and not after:
                self.record(
                    step["id"], "awaiting-approval",
                    "--decision", "approved", "--by", step["approver"],
                    "--evidence", "Fictional test-only approval; no real human authority."
                )
            state = "awaiting-manual" if step["effect"] == "manual" else "running"
            self.record(step["id"], state)
            for artifact in step["outputs"]:
                (artifacts / (artifact + ".txt")).write_text(
                    "Synthetic acceptance artifact; no external operation occurred.\n"
                )
            if after:
                self.record(
                    step["id"], "awaiting-approval", "--evidence",
                    "Draft exists in docs/work; waiting for output acceptance."
                )
                self.record(
                    step["id"], "awaiting-approval",
                    "--decision", "approved", "--by", step["approver"],
                    "--evidence", "Fictional output acceptance after inspecting draft."
                )
            self.record(
                step["id"], "completed", "--evidence",
                "Synthetic verified artifacts in docs/work; no real PR was created."
            )
        history = json.loads((self.target / ".harness/runs/demo.json").read_text())
        self.assertTrue(
            all(state["status"] == "completed" for state in history["steps"].values())
        )
        self.assertEqual(
            (self.target / "README.md").read_text(),
            "Customer changed their readme\n",
        )
        self.cli("check", "--package", ".")
        self.assertTrue(check_package(self.package)["ok"])

    def test_denied_brief_cannot_start_or_enable_dependents(self):
        self.record("clarify", "running")
        self.record(
            "clarify", "awaiting-approval", "--decision", "denied",
            "--by", "product-owner", "--evidence", "Fictional owner rejection."
        )
        self.record("clarify", "running", success=False)
        self.record("plan", "running", success=False)
        state = json.loads((self.target / ".harness/runs/demo.json").read_text())
        self.assertEqual(state["steps"]["clarify"]["status"], "cancelled")

    def test_drafting_is_allowed_but_output_acceptance_blocks_completion(self):
        self.record("clarify", "running")
        self.record(
            "clarify", "completed", "--evidence",
            "Draft exists but is not approved.", success=False
        )
        self.record("plan", "running", success=False)
        self.record(
            "clarify", "awaiting-approval", "--evidence", "Draft brief prepared."
        )
        self.record(
            "clarify", "awaiting-approval", "--decision", "approved",
            "--by", "product-owner", "--evidence", "Fictional draft acceptance."
        )
        self.record("clarify", "running", success=False)
        self.record(
            "clarify", "completed", "--evidence", "Accepted draft checked."
        )
        self.record("plan", "running")

    def test_managed_payload_tampering_is_not_a_customer_edit(self):
        managed = self.target / ".agents/skills/hf-plan/SKILL.md"
        managed.write_text(managed.read_text() + "\nUnauthorized change.\n")
        self.cli("check", "--package", ".", success=False)


if __name__ == "__main__":
    unittest.main()
