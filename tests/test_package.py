import hashlib
import json
import re
import subprocess
import sys
from unittest.mock import patch
from fixtures import FixtureCase, write_bundle_manifest
from harness_factory.errors import HarnessError

from harness_factory.package import generate_package, check_package


class PackageCase(FixtureCase):
    def generate(self):
        self.package = self.work / "package"
        return generate_package(
            self.profile, self.workflow, self.scenarios, self.catalog, self.root, self.package
        )

    def add_manifested_worker_resource(self, relative):
        resource = self.root / "skills/worker" / relative
        resource.parent.mkdir(parents=True, exist_ok=True)
        resource.write_bytes(b"cache")
        manifest_path = self.root / "skills/worker/bundle.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["resources"][relative] = hashlib.sha256(b"cache").hexdigest()
        payload = {
            "schema_version": 2,
            "skill_id": "worker",
            "resources": manifest["resources"],
        }
        manifest["digest"] = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        manifest_path.write_text(json.dumps(manifest))
        self.evidence["bundles"]["worker"] = manifest["digest"]
        (self.root / "evidence.json").write_text(json.dumps(self.evidence))


class PackageTests(PackageCase):
    def test_generate_complete_portable_package_and_minimal_customer(self):
        result = self.generate()
        self.assertTrue(result["ok"])
        self.assertTrue(check_package(self.package)["ok"])
        customer = json.loads((self.package / ".harness/customer.json").read_text())
        self.assertEqual(customer["facts"], [])
        self.assertEqual(customer["pains"], [])
        payload = "\n".join(p.read_text() for p in self.package.rglob("*") if p.is_file())
        self.assertNotIn("private fact", payload)
        self.assertNotIn("private evidence", payload)
        self.assertTrue((self.package / ".agents/skills/customer-rules/SKILL.md").is_file())
        self.assertTrue((self.package / ".agents/skills/issue-flow/SKILL.md").is_file())
        self.assertEqual(
            json.loads((self.package / ".harness/scenarios.json").read_text()),
            self.scenarios,
        )
        self.assertTrue((self.package / "harness_factory/evaluation.py").is_file())
        result = subprocess.run([sys.executable, "-m", "harness_factory", "check", "--package", "."],
                                cwd=self.package, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["ok"])

    def test_tampering_and_extra_payload_rejected(self):
        self.generate()
        p = self.package / "unlisted.txt"
        p.write_text("extra")
        with self.assertRaisesRegex(HarnessError, "unlisted|manifest"):
            check_package(self.package)
        p.unlink()
        p = self.package / ".harness/workflow.json"
        p.write_text("{}")
        with self.assertRaisesRegex(HarnessError, "hash|changed"):
            check_package(self.package)

    def test_generated_package_rejects_tampered_skill_reference(self):
        source = self.root / "skills/worker"
        (source / "references").mkdir()
        (source / "references/guide.md").write_text("Fixture guide.\n")
        bundle = write_bundle_manifest(source, "worker")
        self.evidence["bundles"]["worker"] = bundle["digest"]
        (self.root / "evidence.json").write_text(json.dumps(self.evidence))
        self.generate()
        reference = self.package / ".agents/skills/worker/references/guide.md"
        reference.write_text(reference.read_text() + "\ntampered")
        with self.assertRaisesRegex(HarnessError, "hash|changed"):
            check_package(self.package)

    def test_generated_package_provenance_includes_bundle_identity(self):
        self.generate()
        provenance = json.loads(
            (self.package / ".harness/provenance.json").read_text()
        )["skills"]
        expected = {
            skill["id"]: json.loads(
                (self.root / skill["path"] / "bundle.json").read_text()
            )["digest"]
            for skill in self.catalog["skills"]
        }

        self.assertEqual(
            {row["id"]: row["bundle_digest"] for row in provenance},
            expected,
        )

    def test_existing_output_refused(self):
        self.generate()
        with self.assertRaises(HarnessError):
            generate_package(
                self.profile, self.workflow, self.scenarios, self.catalog, self.root, self.package
            )

    def test_scenarios_must_match_generated_workflow(self):
        self.scenarios["workflow"] = "other-flow"
        with self.assertRaisesRegex(HarnessError, "workflow mismatch"):
            self.generate()
        self.assertFalse(self.package.exists())

    def test_cache_and_run_records_only_exceptions(self):
        self.generate()
        (self.package / ".harness/runs").mkdir()
        (self.package / ".harness/runs/a.json").write_text("{}")
        (self.package / "harness_factory/__pycache__").mkdir(exist_ok=True)
        (self.package / "harness_factory/__pycache__/a.pyc").write_bytes(b"cache")
        self.assertTrue(check_package(self.package)["ok"])
        (self.package / "harness_factory/__pycache__/payload.py").write_text("bad")
        with self.assertRaises(HarnessError):
            check_package(self.package)

    def test_symlink_resource_rejected_before_generation(self):
        (self.root / "skills/worker/link").symlink_to(self.root / "license.txt")
        with self.assertRaises(HarnessError):
            self.generate()
        self.assertFalse(self.package.exists())

    def test_pycache_directory_rejected_before_generation(self):
        self.add_manifested_worker_resource("__pycache__/note.txt")

        with self.assertRaisesRegex(HarnessError, "invalid cache resource"):
            self.generate()
        self.assertFalse(self.package.exists())

    def test_pyc_file_rejected_before_generation(self):
        self.add_manifested_worker_resource("compiled.pyc")

        with self.assertRaisesRegex(HarnessError, "invalid cache resource"):
            self.generate()
        self.assertFalse(self.package.exists())

    def test_malformed_manifest_and_workflow_return_domain_errors(self):
        from harness_factory.package import hash_bytes, json_bytes
        self.generate()
        workflow_path = self.package / ".harness/workflow.json"
        workflow = json.loads(workflow_path.read_text())
        workflow["id"] = []
        workflow_path.write_bytes(json_bytes(workflow))
        manifest_path = self.package / ".harness/manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["workflow_id"] = []
        manifest["files"][".harness/workflow.json"] = hash_bytes(workflow_path.read_bytes())
        manifest_path.write_bytes(json_bytes(manifest))
        with self.assertRaises(HarnessError):
            check_package(self.package)

    def test_tracker_runtime_module_is_required(self):
        from harness_factory.package import json_bytes
        self.generate()
        tracker = self.package / "harness_factory/tracker.py"
        tracker.unlink()
        manifest_path = self.package / ".harness/manifest.json"
        manifest = json.loads(manifest_path.read_text())
        del manifest["files"]["harness_factory/tracker.py"]
        manifest_path.write_bytes(json_bytes(manifest))
        with self.assertRaisesRegex(HarnessError, "required files"):
            check_package(self.package)

    def test_skill_bundle_runtime_module_is_required(self):
        from harness_factory.package import json_bytes
        self.generate()
        skill_bundle = self.package / "harness_factory/skill_bundle.py"
        skill_bundle.unlink()
        manifest_path = self.package / ".harness/manifest.json"
        manifest = json.loads(manifest_path.read_text())
        del manifest["files"]["harness_factory/skill_bundle.py"]
        manifest_path.write_bytes(json_bytes(manifest))
        with self.assertRaisesRegex(HarnessError, "required files"):
            check_package(self.package)

    def test_unreadable_tree_is_not_silently_omitted(self):
        self.generate()
        from harness_factory.package import inventory
        def walk(root, **kwargs):
            if "onerror" in kwargs:
                kwargs["onerror"](PermissionError("blocked directory"))
            return iter([])
        with patch("os.walk", side_effect=walk), self.assertRaises(OSError):
            inventory(self.package)

    def test_package_level_public_api_supports_delivery(self):
        import harness_factory as hf
        self.assertTrue(hasattr(hf, "validate"), "public API missing")
        hf.validate(self.profile, self.workflow, self.catalog, self.root)
        package, target = self.work / "public-package", self.work / "public-target"
        hf.generate_package(
            self.profile, self.workflow, self.scenarios, self.catalog, self.root, package
        )
        preview = hf.plan_install(package, target)
        hf.apply_install(package, target, preview["digest"])
        self.assertTrue(hf.check_package(target)["ok"])
        self.assertEqual(hf.load_json(target / ".harness/customer.json")["customer_id"], "acme")

    def test_reserved_skill_collision_and_output_symlink_do_not_mutate(self):
        self.workflow["id"] = "worker"
        self.scenarios["workflow"] = "worker"
        with self.assertRaisesRegex(HarnessError, "collision"):
            self.generate()
        self.assertFalse(self.package.exists())
        self.workflow["id"] = "issue-flow"
        self.scenarios["workflow"] = "issue-flow"
        link = self.work / "link"
        link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(HarnessError, "symlink"):
            generate_package(
                self.profile, self.workflow, self.scenarios, self.catalog, self.root, link / "new"
            )
        self.assertFalse((self.root / "new").exists())

    def test_customer_execution_unknowns_are_preserved_and_generated_links_resolve(self):
        self.profile["unknowns"] = ["Repository write permission remains unverified"]
        self.profile["constraints"] = ["No automatic publication"]
        self.generate()
        customer = json.loads((self.package / ".harness/customer.json").read_text())
        for field in ("systems", "constraints", "glossary", "roles", "unknowns"):
            self.assertEqual(customer[field], self.profile[field])
        entry = self.package / ".agents/skills/issue-flow/SKILL.md"
        for link in re.findall(r"\[[^\]]*\]\(([^)]+)\)", entry.read_text()):
            with self.subTest(link=link):
                self.assertTrue((entry.parent / link).is_file())

    def test_generated_guide_lists_actual_bindings_and_customer_git_exclusions(self):
        self.profile["systems"] += [
            {"id": "tickets", "kind": "issues", "tool": "mcp:customer-tickets", "capabilities": ["issue-read"]},
            {"id": "legacy", "kind": "issues", "tool": "custom-tracker", "capabilities": ["lookup"]},
        ]
        self.generate()
        guide = (self.package / "INSTALL.md").read_text()
        for value in ("github.issue-read", "github.issue-create", "tickets.issue-read", "mcp:customer-tickets",
                      "legacy.lookup", "custom-tracker", ".gitignore", ".harness/runs/", "__pycache__/"):
            with self.subTest(value=value):
                self.assertIn(value, guide)
        self.assertIn("native Copilot", guide)
        self.assertIn("credentials", guide)
        self.assertIn("manual/unverified", guide)
        self.assertIn(
            "Primary handoff/readiness check: `python3 -m harness_factory delivery-check --package .`.",
            guide,
        )
        self.assertIn(
            "With separate consent for bounded read-only probes: "
            "`python3 -m harness_factory delivery-check --package . --allow-read-probes`.",
            guide,
        )
        self.assertIn("`ok: true` means the check ran; only `ready: true` means", guide)
        self.assertIn(
            "The evaluation receipt can be current while the customer environment remains unverified.",
            guide,
        )
        self.assertIn("lower-level diagnostic", guide)

    def test_generated_guide_explains_issue_tracker_connection(self):
        self.generate()
        install = (self.package / "INSTALL.md").read_text()
        self.assertTrue(
            (
                self.package
                / ".agents/skills/hf-issues-markdown/SKILL.md"
            ).is_file()
        )
        packaged_catalog = json.loads(
            (self.package / ".harness/catalog.json").read_text()
        )
        self.assertIn(
            "hf-issues-markdown",
            {skill["id"] for skill in packaged_catalog["skills"]},
        )
        self.assertIn("## Issue tracker connection", install)
        self.assertIn("Git + Markdown", install)
        self.assertIn("issues/<issue-id>.md", install)
        self.assertIn(
            "tracker-guide --profile .harness/customer.json --target .",
            install,
        )
        self.assertIn("does not verify", install)

    def test_github_mcp_guide_names_provider_and_native_setup(self):
        self.profile["issue_tracker"].update(
            provider="github",
            connection="mcp",
            project="acme/widgets",
            path=None,
            skill=None,
            mcp="mcp:github",
        )
        self.profile["systems"][0]["tool"] = "mcp:github"
        self.generate()
        install = (self.package / "INSTALL.md").read_text()
        self.assertIn("GitHub Issues", install)
        self.assertIn("/mcp", install)

    def test_after_approval_entry_orders_draft_submission_decision_and_completion(self):
        self.workflow["steps"][0].update(approval=True, approver="owner", approval_timing="after")
        self.generate()
        entry = (self.package / ".agents/skills/issue-flow/SKILL.md").read_text()
        running = entry.index("--status running")
        submission = entry.index("--status awaiting-approval")
        decision = entry.index("--decision approved")
        completed = entry.index("--status completed")
        self.assertLess(running, submission)
        self.assertLess(submission, decision)
        self.assertLess(decision, completed)
        self.assertIn("draft", entry.lower())
        self.assertNotIn("BEFORE the action", entry)

    def test_missing_references_reject_generation_and_rewritten_manifest_check(self):
        from harness_factory.package import json_bytes
        self.write_skill_body("[Required](references/guide.md)\n")
        with self.assertRaisesRegex(HarnessError, "reference"):
            self.generate()
        self.assertFalse(self.package.exists())
        references = self.root / "skills/worker/references"
        references.mkdir()
        (references / "guide.md").write_text("Required bundled guide\n")
        bundle = write_bundle_manifest(self.root / "skills/worker", "worker")
        self.evidence["bundles"]["worker"] = bundle["digest"]
        (self.root / "evidence.json").write_text(json.dumps(self.evidence))
        self.generate()
        relative = ".agents/skills/worker/references/guide.md"
        (self.package / relative).unlink()
        manifest_path = self.package / ".harness/manifest.json"
        manifest = json.loads(manifest_path.read_text())
        del manifest["files"][relative]
        manifest_path.write_bytes(json_bytes(manifest))
        with self.assertRaisesRegex(HarnessError, "reference|bundle|resource"):
            check_package(self.package)
