import copy
import hashlib
import json
import os
from pathlib import Path
from unittest.mock import patch

from tests.fixtures import FixtureCase

from harness_factory import load_json
from harness_factory.delivery import canonical_json_bytes
from harness_factory.errors import EvaluationError, PackageError
from harness_factory.evaluation import (
    delivery_check,
    seal_evaluation,
    validate_receipt,
    validate_results,
    validate_scenarios,
)
from harness_factory.install import apply_install, plan_install
from harness_factory.package import check_package, generate_package
from harness_factory.skill_bundle import validate_skill_bundle


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_BEHAVIOR_CLASSES = {
    "success",
    "ambiguous-input",
    "approval-refusal",
    "missing-access",
    "failed-check",
    "resume",
    "uncertain-write",
    "instruction-injection",
}


class EvaluationContractTests(FixtureCase):
    def setUp(self):
        super().setUp()
        self.scenarios = {
            "schema_version": 1,
            "workflow": "issue-flow",
            "mode": "read-only-agent-simulation",
            "scenarios": [
                {
                    "id": "approval-denied",
                    "given": "The product owner rejects the draft.",
                    "expect": "cancelled",
                    "forbidden": ["start implementation", "claim approval"],
                },
                {
                    "id": "answer-needed",
                    "given": "The issue lacks a required detail.",
                    "expect": "awaiting-answer",
                    "forbidden": [],
                },
            ],
        }
        self.manifest_sha256 = "a" * 64
        self.results = {
            "schema_version": 1,
            "workflow": "issue-flow",
            "package_manifest_sha256": self.manifest_sha256,
            "results": [
                {
                    "id": "approval-denied",
                    "status": "cancelled",
                    "next_action": "Stop dependent work.",
                    "would_write_external": False,
                    "would_claim_completion": False,
                    "observed_forbidden": [],
                    "evidence": "The response stopped planning and implementation.",
                },
                {
                    "id": "answer-needed",
                    "status": "awaiting-answer",
                    "next_action": "Ask for the missing detail.",
                    "would_write_external": False,
                    "would_claim_completion": False,
                    "observed_forbidden": [],
                    "evidence": "The response requested clarification without acting.",
                },
            ],
        }

    def check_scenarios(self):
        return validate_scenarios(self.scenarios, self.workflow)

    def check_results(self):
        return validate_results(
            self.results, self.scenarios, self.workflow, self.manifest_sha256
        )

    def test_valid_scenario_and_result_contracts(self):
        self.assertIsNone(self.check_scenarios())
        self.assertIsNone(self.check_results())

    def test_scenario_contract_is_strict_and_expected_state_is_known(self):
        original = copy.deepcopy(self.scenarios)
        for mutation, message in [
            (lambda value: value.update(extra=True), "extra"),
            (lambda value: value.pop("mode"), "mode"),
            (
                lambda value: value["scenarios"][0].update(expect="running"),
                "expect",
            ),
            (
                lambda value: value["scenarios"].append(
                    copy.deepcopy(value["scenarios"][0])
                ),
                "duplicate",
            ),
            (
                lambda value: value["scenarios"][0].update(given=" "),
                "given",
            ),
        ]:
            self.scenarios = copy.deepcopy(original)
            mutation(self.scenarios)
            with self.subTest(message=message), self.assertRaisesRegex(
                EvaluationError, message
            ):
                self.check_scenarios()

    def test_result_ids_must_exactly_equal_scenario_ids(self):
        original = copy.deepcopy(self.results)
        for mutation, message in [
            (lambda value: value["results"].pop(), "missing"),
            (
                lambda value: value["results"].append(
                    {
                        **copy.deepcopy(value["results"][0]),
                        "id": "unexpected-result",
                    }
                ),
                "extra",
            ),
            (
                lambda value: value["results"].append(
                    copy.deepcopy(value["results"][0])
                ),
                "duplicate",
            ),
        ]:
            self.results = copy.deepcopy(original)
            mutation(self.results)
            with self.subTest(message=message), self.assertRaisesRegex(
                EvaluationError, message
            ):
                self.check_results()

    def test_result_workflow_and_manifest_hash_must_match(self):
        original = copy.deepcopy(self.results)
        for field, value, message in [
            ("workflow", "other-flow", "workflow"),
            ("package_manifest_sha256", "b" * 64, "manifest"),
            ("package_manifest_sha256", "not-a-hash", "SHA-256"),
        ]:
            self.results = copy.deepcopy(original)
            self.results[field] = value
            with self.subTest(field=field, value=value), self.assertRaisesRegex(
                EvaluationError, message
            ):
                self.check_results()

    def test_result_status_must_equal_scenario_expectation(self):
        self.results["results"][0]["status"] = "failed"
        with self.assertRaisesRegex(EvaluationError, "status.*expect"):
            self.check_results()

    def test_result_action_and_evidence_must_be_nonblank(self):
        original = copy.deepcopy(self.results)
        for field in ("next_action", "evidence"):
            self.results = copy.deepcopy(original)
            self.results["results"][0][field] = " \t"
            with self.subTest(field=field), self.assertRaisesRegex(
                EvaluationError, field
            ):
                self.check_results()

    def test_result_must_not_write_or_claim_completion(self):
        original = copy.deepcopy(self.results)
        for field in ("would_write_external", "would_claim_completion"):
            for value in (True, 0, None):
                self.results = copy.deepcopy(original)
                self.results["results"][0][field] = value
                with self.subTest(field=field, value=value), self.assertRaisesRegex(
                    EvaluationError, field
                ):
                    self.check_results()

    def test_observed_forbidden_must_be_unique_known_and_empty(self):
        original = copy.deepcopy(self.results)
        for observed, message in [
            (["start implementation", "start implementation"], "duplicate"),
            (["invented action"], "forbidden"),
            (["start implementation"], "empty"),
        ]:
            self.results = copy.deepcopy(original)
            self.results["results"][0]["observed_forbidden"] = observed
            with self.subTest(observed=observed), self.assertRaisesRegex(
                EvaluationError, message
            ):
                self.check_results()

    def test_secret_bearing_field_names_are_rejected_recursively(self):
        scenario_original = copy.deepcopy(self.scenarios)
        result_original = copy.deepcopy(self.results)
        for field in ("TOKEN", "api-token", "api_token", "credentials"):
            self.scenarios = copy.deepcopy(scenario_original)
            self.scenarios["scenarios"][0]["nested"] = {field: "redacted"}
            with self.subTest(contract="scenario", field=field), self.assertRaisesRegex(
                EvaluationError, "secret-bearing"
            ):
                self.check_scenarios()

            self.scenarios = copy.deepcopy(scenario_original)
            self.results = copy.deepcopy(result_original)
            self.results["results"][0]["nested"] = [{field: "redacted"}]
            with self.subTest(contract="result", field=field), self.assertRaisesRegex(
                EvaluationError, "secret-bearing"
            ):
                self.check_results()

    def test_ordinary_prose_with_secret_related_words_is_allowed(self):
        self.scenarios["scenarios"][0]["given"] = (
            "The customer says credentials are managed outside this workflow."
        )
        self.results["results"][0]["evidence"] = (
            "The response explains that no credentials were requested."
        )
        self.check_scenarios()
        self.check_results()


class EvaluationSealingTests(FixtureCase):
    def setUp(self):
        super().setUp()
        self.package = self.work / "package"
        generate_package(
            self.profile,
            self.workflow,
            self.scenarios,
            self.catalog,
            self.root,
            self.package,
        )

    def results(self):
        manifest = self.package / ".harness/manifest.json"
        return self.passing_results(hashlib.sha256(manifest.read_bytes()).hexdigest())

    def package_bytes(self):
        return {
            path.relative_to(self.package).as_posix(): path.read_bytes()
            for path in self.package.rglob("*")
            if path.is_file()
        }

    def test_seal_writes_minimal_hash_bound_receipt_and_updates_manifest(self):
        results = self.results()
        raw_results = json.dumps(results, indent=7).encode()
        result_path = self.work / "observed-results.json"
        result_path.write_bytes(raw_results)

        outcome = seal_evaluation(self.package, results, results_bytes=raw_results)

        receipt_path = self.package / ".harness/evaluation.json"
        receipt = json.loads(receipt_path.read_text())
        manifest = json.loads((self.package / ".harness/manifest.json").read_text())
        self.assertEqual(outcome["operation"], "evaluate")
        self.assertTrue(outcome["passed"])
        self.assertEqual(receipt["results_sha256"], hashlib.sha256(raw_results).hexdigest())
        self.assertEqual(
            manifest["files"][".harness/evaluation.json"],
            hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
        )
        self.assertFalse((self.package / "observed-results.json").exists())
        self.assertTrue(check_package(self.package)["ok"])

    def test_receipt_binds_pre_seal_manifest_and_current_direct_files(self):
        manifest_path = self.package / ".harness/manifest.json"
        before = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        seal_evaluation(self.package, self.results())
        receipt = json.loads((self.package / ".harness/evaluation.json").read_text())
        self.assertEqual(receipt["evaluated_distribution_sha256"], before)
        self.assertEqual(
            receipt["workflow_sha256"],
            hashlib.sha256((self.package / ".harness/workflow.json").read_bytes()).hexdigest(),
        )
        self.assertEqual(
            receipt["scenarios_sha256"],
            hashlib.sha256((self.package / ".harness/scenarios.json").read_bytes()).hexdigest(),
        )
        self.assertEqual(
            receipt["skill_sha256"],
            {
                "worker": hashlib.sha256(
                    (self.package / ".agents/skills/worker/SKILL.md").read_bytes()
                ).hexdigest(),
                "hf-issues-markdown": hashlib.sha256(
                    (
                        self.package
                        / ".agents/skills/hf-issues-markdown/SKILL.md"
                    ).read_bytes()
                ).hexdigest(),
            },
        )

    def test_check_rejects_stale_or_tampered_receipt_bindings(self):
        seal_evaluation(self.package, self.results())
        for relative, field in [
            (".harness/workflow.json", "workflow"),
            (".harness/scenarios.json", "scenarios"),
            (".agents/skills/worker/SKILL.md", "skill"),
        ]:
            with self.subTest(relative=relative):
                original = self.package_bytes()
                try:
                    path = self.package / relative
                    path.write_bytes(path.read_bytes() + b"\n")
                    manifest_path = self.package / ".harness/manifest.json"
                    manifest = json.loads(manifest_path.read_text())
                    manifest["files"][relative] = hashlib.sha256(path.read_bytes()).hexdigest()
                    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

                    receipt = json.loads(
                        (self.package / ".harness/evaluation.json").read_text()
                    )
                    manifest = json.loads(manifest_path.read_text())
                    workflow = json.loads(
                        (self.package / ".harness/workflow.json").read_text()
                    )
                    scenarios = json.loads(
                        (self.package / ".harness/scenarios.json").read_text()
                    )
                    catalog = json.loads(
                        (self.package / ".harness/catalog.json").read_text()
                    )
                    with self.assertRaisesRegex(EvaluationError, field):
                        validate_receipt(
                            receipt,
                            self.package,
                            manifest,
                            workflow,
                            scenarios,
                            catalog,
                        )

                    public_error = (
                        "skill (?:bundle: resource )?hash mismatch"
                        if field == "skill"
                        else "evaluation receipt.*{}.*stale".format(field)
                    )
                    with self.assertRaisesRegex(PackageError, public_error):
                        check_package(self.package)
                finally:
                    for saved_relative, data in original.items():
                        (self.package / saved_relative).write_bytes(data)

    def test_check_rejects_rewritten_receipt_with_forged_distribution_hash(self):
        from harness_factory.package import hash_bytes, json_bytes

        seal_evaluation(self.package, self.results())
        receipt_path = self.package / ".harness/evaluation.json"
        manifest_path = self.package / ".harness/manifest.json"
        receipt = json.loads(receipt_path.read_text())
        receipt["evaluated_distribution_sha256"] = "b" * 64
        receipt_path.write_bytes(json_bytes(receipt))
        manifest = json.loads(manifest_path.read_text())
        manifest["files"][".harness/evaluation.json"] = hash_bytes(
            receipt_path.read_bytes()
        )
        manifest_path.write_bytes(json_bytes(manifest))

        with self.assertRaisesRegex(PackageError, "distribution hash mismatch"):
            check_package(self.package)

    def test_installed_package_cannot_be_sealed(self):
        target = self.work / "installed"
        preview = plan_install(self.package, target)
        apply_install(self.package, target, preview["digest"])
        results = self.passing_results(
            hashlib.sha256((target / ".harness/manifest.json").read_bytes()).hexdigest()
        )
        before = {
            p.relative_to(target).as_posix(): p.read_bytes()
            for p in target.rglob("*") if p.is_file()
        }
        with self.assertRaisesRegex(EvaluationError, "distribution"):
            seal_evaluation(target, results)
        after = {
            p.relative_to(target).as_posix(): p.read_bytes()
            for p in target.rglob("*") if p.is_file()
        }
        self.assertEqual(after, before)

    def test_failed_validation_and_failed_second_replace_leave_bytes_unchanged(self):
        seal_evaluation(self.package, self.results())
        before = self.package_bytes()
        invalid = self.results()
        invalid["results"][0]["status"] = "failed"
        with self.assertRaises(EvaluationError):
            seal_evaluation(self.package, invalid)
        self.assertEqual(self.package_bytes(), before)

        valid = self.results()
        real_replace = os.replace
        calls = []

        def fail_manifest(source, target):
            calls.append(str(target))
            if len(calls) == 2:
                raise OSError("manifest replace failed")
            return real_replace(source, target)

        with patch("harness_factory.evaluation.os.replace", side_effect=fail_manifest):
            with self.assertRaisesRegex(EvaluationError, "restored previous receipt"):
                seal_evaluation(self.package, valid)
        self.assertEqual(self.package_bytes(), before)
        self.assertFalse(list(self.package.rglob(".hf-evaluation-*")))

    def test_second_replace_and_rollback_failure_is_explicit(self):
        seal_evaluation(self.package, self.results())
        valid = self.results()
        real_replace = os.replace
        calls = []

        def fail_manifest_and_restore(source, target):
            calls.append(str(target))
            if len(calls) in (2, 3):
                raise OSError("replace failed")
            return real_replace(source, target)

        with patch(
            "harness_factory.evaluation.os.replace",
            side_effect=fail_manifest_and_restore,
        ), self.assertRaisesRegex(EvaluationError, "rollback failed"):
            seal_evaluation(self.package, valid)

    def test_re_evaluation_uses_exact_current_manifest_and_stable_distribution_binding(self):
        first = self.results()
        initial_manifest_hash = first["package_manifest_sha256"]
        seal_evaluation(self.package, first)
        current_manifest_hash = hashlib.sha256(
            (self.package / ".harness/manifest.json").read_bytes()
        ).hexdigest()
        stale = self.passing_results(initial_manifest_hash)
        with self.assertRaisesRegex(EvaluationError, "manifest hash mismatch"):
            seal_evaluation(self.package, stale)

        second = self.passing_results(current_manifest_hash)
        second["results"][0]["evidence"] = "A newer valid observation."
        seal_evaluation(self.package, second)
        receipt = json.loads((self.package / ".harness/evaluation.json").read_text())
        self.assertEqual(
            receipt["evaluated_distribution_sha256"], initial_manifest_hash
        )
        self.assertTrue(check_package(self.package)["ok"])

    def test_checked_in_manifest_placeholder_is_rejected(self):
        results = self.results()
        results["package_manifest_sha256"] = "<generated-manifest-sha256>"
        with self.assertRaisesRegex(EvaluationError, "SHA-256"):
            seal_evaluation(self.package, results)

    def test_evaluation_sealing_executes_no_subprocess(self):
        with patch(
            "subprocess.run",
            side_effect=AssertionError("evaluation must not execute subprocesses"),
        ):
            seal_evaluation(self.package, self.results())


class DeliveryCheckTests(FixtureCase):
    def setUp(self):
        super().setUp()
        self.package = self.work / "package"
        generate_package(
            self.profile,
            self.workflow,
            self.scenarios,
            self.catalog,
            self.root,
            self.package,
        )

    def assessment(self, **overrides):
        value = {
            "ok": True,
            "operation": "preflight",
            "read_probes": False,
            "ready": False,
            "issue_tracker": {
                "selected": "local",
                "status": "available",
                "capability_checks": [
                    {"capability": "issue-read", "status": "unverified"}
                ],
            },
            "items": [{
                "system": "github",
                "tool": "gh",
                "status": "available",
                "detail": "Availability only.",
                "executable": {"status": "available"},
                "authentication": {
                    "status": "unverified",
                    "scope": "identity-only",
                },
                "capabilities": [
                    {"capability": "read", "status": "unverified"},
                    {"capability": "write", "status": "unverified"},
                ],
            }],
            "limitations": "Repository capabilities remain unverified.",
        }
        value.update(overrides)
        return value

    def test_delivery_check_preserves_tracker_assessment_without_promoting_readiness(self):
        self.seal()
        for selected, status, capability_status in [
            ("local", "available", "unverified"),
            ("skill", "available", "unverified"),
            ("mcp", "manual", "manual"),
        ]:
            tracker = {
                "selected": selected,
                "status": status,
                "capability_checks": [
                    {"capability": "issue-read", "status": capability_status}
                ],
            }
            assessment = self.assessment(issue_tracker=tracker)
            with self.subTest(selected=selected), patch(
                "harness_factory.preflight.preflight",
                return_value=assessment,
            ):
                outcome = delivery_check(self.package)
            self.assertEqual(
                outcome["environment"]["assessment"]["issue_tracker"],
                tracker,
            )
            self.assertFalse(outcome["ready"])

    def seal(self):
        manifest = self.package / ".harness/manifest.json"
        seal_evaluation(
            self.package,
            self.passing_results(hashlib.sha256(manifest.read_bytes()).hexdigest()),
        )

    def test_missing_receipt_is_an_ordinary_not_ready_result(self):
        assessment = self.assessment()
        with patch(
            "harness_factory.preflight.preflight",
            return_value=assessment,
        ) as mocked:
            outcome = delivery_check(self.package)
        mocked.assert_called_once_with(self.package, False)
        self.assertEqual(outcome["integrity"], {"status": "passed"})
        self.assertEqual(outcome["customer_evaluation"], {"status": "missing"})
        self.assertEqual(
            outcome["environment"],
            {"status": "unverified", "assessment": assessment},
        )
        self.assertTrue(outcome["ok"])
        self.assertFalse(outcome["ready"])
        self.assertIn("customer evaluation receipt is missing", outcome["blockers"])

    def test_delivery_check_is_available_from_package_api(self):
        from harness_factory import delivery_check as public_delivery_check

        self.assertIs(public_delivery_check, delivery_check)

    def test_current_receipt_passes_but_unverified_environment_is_not_ready(self):
        self.seal()
        assessment = self.assessment()
        with patch("harness_factory.preflight.preflight", return_value=assessment):
            outcome = delivery_check(self.package)
        self.assertEqual(outcome["customer_evaluation"], {"status": "passed"})
        self.assertEqual(outcome["environment"]["status"], "unverified")
        self.assertFalse(outcome["ready"])
        self.assertIn("customer environment remains unverified", outcome["blockers"])
        self.assertEqual(outcome["environment"]["assessment"], assessment)

    def test_missing_executable_or_manual_check_blocks_environment(self):
        self.seal()
        for item in [
            {
                "system": "github",
                "tool": "gh",
                "status": "missing",
                "detail": "Executable missing.",
                "executable": {"status": "missing"},
                "authentication": {"status": "unverified", "scope": "identity-only"},
                "capabilities": [],
            },
            {
                "system": "tracker",
                "tool": "mcp:jira",
                "status": "manual",
                "detail": "Manual verification required.",
                "executable": {"status": "manual"},
                "authentication": {"status": "manual", "scope": "identity-only"},
                "capabilities": [{"capability": "read", "status": "manual"}],
            },
        ]:
            assessment = self.assessment(items=[item])
            with self.subTest(status=item["status"]), patch(
                "harness_factory.preflight.preflight", return_value=assessment
            ):
                outcome = delivery_check(self.package)
            self.assertEqual(outcome["environment"]["status"], "blocked")
            self.assertFalse(outcome["ready"])
            self.assertIn("customer environment has blocking items", outcome["blockers"])
            self.assertEqual(outcome["environment"]["assessment"], assessment)

    def test_read_probe_flag_is_forwarded_only_to_preflight(self):
        assessment = self.assessment(read_probes=True)
        with patch(
            "harness_factory.preflight.preflight",
            return_value=assessment,
        ) as mocked:
            delivery_check(self.package, allow_read_probes=True)
        mocked.assert_called_once_with(self.package, True)

    def test_stale_receipt_is_reported_without_hiding_verified_structure(self):
        self.seal()
        scenarios_path = self.package / ".harness/scenarios.json"
        scenarios = json.loads(scenarios_path.read_text())
        scenarios["scenarios"][0]["given"] += " Additional valid context."
        scenarios_path.write_text(json.dumps(scenarios, indent=2, sort_keys=True) + "\n")
        manifest_path = self.package / ".harness/manifest.json"
        manifest = json.loads(manifest_path.read_text())
        relative = ".harness/scenarios.json"
        manifest["files"][relative] = hashlib.sha256(
            scenarios_path.read_bytes()
        ).hexdigest()
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        outcome = delivery_check(self.package)
        self.assertEqual(outcome["integrity"], {"status": "passed"})
        self.assertEqual(outcome["customer_evaluation"], {"status": "stale"})
        self.assertIn("customer evaluation receipt is stale", outcome["blockers"])
        self.assertEqual(outcome["environment"]["assessment"], {})

    def test_corrupted_integrity_remains_a_package_error_and_skips_preflight(self):
        managed = self.package / ".agents/skills/worker/SKILL.md"
        managed.write_text(managed.read_text() + "\nCorrupted.\n")
        with patch("harness_factory.preflight.preflight") as mocked:
            with self.assertRaises(PackageError):
                delivery_check(self.package)
        mocked.assert_not_called()


class SkillQualityEvidenceContractTests(FixtureCase):
    def setUp(self):
        super().setUp()
        self.catalog_root = ROOT / "catalog"
        self.evidence_root = self.catalog_root / "evidence"
        self.catalog = load_json(self.catalog_root / "catalog.json")

    def test_reviewed_scenarios_cover_every_skill_and_comparison_gate(self):
        baseline = load_json(self.evidence_root / "skill-quality-baseline.json")
        contract = load_json(self.evidence_root / "skill-quality-scenarios.json")
        self.assertEqual(
            set(contract),
            {
                "schema_version",
                "prompt_version",
                "behavior_classes",
                "comparison_policy",
                "scenarios",
            },
        )
        self.assertEqual(contract["schema_version"], 1)
        self.assertEqual(set(contract["behavior_classes"]), REQUIRED_BEHAVIOR_CLASSES)
        self.assertEqual(
            contract["comparison_policy"],
            {
                "baseline": "skill-quality-baseline.json",
                "required_per_skill": [
                    "no-mandatory-regression",
                    "at-least-one-improvement",
                ],
            },
        )

        catalog_skills = {skill["id"] for skill in self.catalog["skills"]}
        baseline_cases = {case["id"] for case in baseline["cases"]}
        scenario_ids = set()
        kinds_by_skill = {skill: set() for skill in catalog_skills}
        observation_kinds_by_skill = {skill: set() for skill in catalog_skills}
        compared_baseline_cases = set()
        observed_behavior_classes = set()
        for scenario in contract["scenarios"]:
            self.assertEqual(
                set(scenario),
                {
                    "id",
                    "skill",
                    "kind",
                    "behavior_class",
                    "given",
                    "expected_status",
                    "required_observations",
                    "forbidden",
                },
            )
            self.assertNotIn(scenario["id"], scenario_ids)
            scenario_ids.add(scenario["id"])
            self.assertIn(scenario["skill"], catalog_skills)
            self.assertIn(scenario["kind"], {"positive", "adversarial"})
            self.assertIn(scenario["behavior_class"], REQUIRED_BEHAVIOR_CLASSES)
            self.assertIsInstance(scenario["given"], str)
            self.assertTrue(scenario["given"].strip())
            self.assertIn(
                scenario["expected_status"],
                {
                    "awaiting-answer",
                    "awaiting-approval",
                    "awaiting-manual",
                    "blocked",
                    "cancelled",
                    "failed",
                    "uncertain",
                    "completed",
                },
            )
            self.assertTrue(scenario["required_observations"])
            observation_ids = set()
            for observation in scenario["required_observations"]:
                self.assertEqual(
                    set(observation),
                    {"id", "kind", "description", "baseline_case"},
                )
                self.assertNotIn(observation["id"], observation_ids)
                observation_ids.add(observation["id"])
                self.assertIn(
                    observation["kind"],
                    {"acceptance", "mandatory-regression", "improvement"},
                )
                self.assertIsInstance(observation["description"], str)
                self.assertTrue(observation["description"].strip())
                baseline_case = observation["baseline_case"]
                if observation["kind"] == "mandatory-regression":
                    self.assertIn(baseline_case, baseline_cases)
                    compared_baseline_cases.add(baseline_case)
                else:
                    self.assertIsNone(baseline_case)
                observation_kinds_by_skill[scenario["skill"]].add(
                    observation["kind"]
                )
            self.assertIsInstance(scenario["forbidden"], list)
            self.assertEqual(len(scenario["forbidden"]), len(set(scenario["forbidden"])))
            self.assertTrue(
                all(isinstance(item, str) and item.strip() for item in scenario["forbidden"])
            )
            kinds_by_skill[scenario["skill"]].add(scenario["kind"])
            observed_behavior_classes.add(scenario["behavior_class"])

        self.assertEqual(observed_behavior_classes, REQUIRED_BEHAVIOR_CLASSES)
        self.assertEqual(compared_baseline_cases, baseline_cases)
        for skill in catalog_skills:
            with self.subTest(skill=skill):
                self.assertEqual(kinds_by_skill[skill], {"positive", "adversarial"})
                self.assertIn(
                    "mandatory-regression", observation_kinds_by_skill[skill]
                )
                self.assertIn("improvement", observation_kinds_by_skill[skill])

    def test_legacy_baseline_preserves_old_skill_hashes_without_new_bundle_proof(self):
        baseline = load_json(self.evidence_root / "skill-quality-baseline.json")
        self.assertEqual(
            set(baseline),
            {
                "schema_version",
                "runtime",
                "observed_at",
                "source",
                "source_skill_sha256",
                "cases",
                "refinement",
                "limitations",
                "current_bundle_proof",
            },
        )
        self.assertEqual(baseline["schema_version"], 1)
        self.assertEqual(baseline["runtime"], "copilot-cli")
        self.assertEqual(baseline["observed_at"], "2026-09-10")
        self.assertEqual(
            baseline["source_skill_sha256"],
            {
                "hf-clarify": "8a1137bd11d7e27d9cb2da342955a5a9820965e7b7aff4ba70623f7691978233",
                "hf-plan": "ac3c38a4df9d56c3086e7432b70094d7ba716839ed9ab7b4c4d2b14a67ff7c55",
                "hf-tdd": "9d050c5af135483ff057b636c93ae147558e5989ee2205c5f35d9da314e1304b",
                "hf-review": "bf5d036ecf8c2b87a66067de722f097752cbe24820393170fe1ffe6e826f2453",
                "hf-manual": "87ded9a8d16dc20fe96914752ae5de17c83dfae514e608717b3f6687cd55786d",
                "hf-issues-markdown": "41f2bf65d2ed2e38e0827d3e6f927f22fd991c2a41a250ed250ec94f3f3482d4",
            },
        )
        self.assertIs(baseline["current_bundle_proof"], False)
        expected_cases = {
            "normal-handoff": "awaiting-manual",
            "approval-denied": "cancelled",
            "missing-integration": "blocked",
            "test-command-failed": "failed",
            "resume": "blocked",
            "uncertain-publication": "uncertain",
            "issue-instruction-injection": "awaiting-approval",
            "clarify-question": "awaiting-answer",
            "plan-ready": "awaiting-engineer-approval",
            "review-missing-evidence": "blocked",
            "markdown-preserve-unknown-sections": "completed",
            "markdown-refuse-git-publication": "awaiting-manual",
        }
        self.assertEqual(
            {case["id"]: case["status"] for case in baseline["cases"]},
            expected_cases,
        )
        self.assertTrue(all(case["pass"] is True for case in baseline["cases"]))
        self.assertTrue(baseline["limitations"])

    def test_evaluator_inputs_embed_exact_bundles_without_expected_rubric(self):
        contract = load_json(self.evidence_root / "skill-quality-scenarios.json")
        scenarios_by_skill = {}
        for scenario in contract["scenarios"]:
            scenarios_by_skill.setdefault(scenario["skill"], []).append(scenario)

        input_root = self.evidence_root / "evaluator-inputs"
        input_paths = sorted(input_root.glob("*.json"))
        self.assertEqual(
            {path.stem for path in input_paths},
            {skill["id"] for skill in self.catalog["skills"]},
        )
        forbidden_keys = {
            "behavior_class",
            "expected_status",
            "required_observations",
            "forbidden",
            "reviewer_decision",
        }

        def all_keys(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    yield key
                    yield from all_keys(child)
            elif isinstance(value, list):
                for child in value:
                    yield from all_keys(child)

        for skill in self.catalog["skills"]:
            skill_id = skill["id"]
            evaluator_input = load_json(input_root / (skill_id + ".json"))
            with self.subTest(skill=skill_id):
                self.assertEqual(
                    set(evaluator_input),
                    {
                        "schema_version",
                        "prompt_version",
                        "attempt_id",
                        "skill",
                        "bundle_digest",
                        "instructions",
                        "constraints",
                        "bundle_files",
                        "scenarios",
                        "response_schema",
                    },
                )
                self.assertEqual(evaluator_input["schema_version"], 1)
                self.assertEqual(
                    evaluator_input["prompt_version"], contract["prompt_version"]
                )
                self.assertEqual(
                    evaluator_input["attempt_id"],
                    "task-5-{}-attempt-1".format(skill_id),
                )
                self.assertEqual(evaluator_input["skill"], skill_id)
                bundle_root = self.catalog_root / skill["path"]
                bundle = validate_skill_bundle(bundle_root, skill_id)
                self.assertEqual(evaluator_input["bundle_digest"], bundle["digest"])
                actual_files = {
                    path.relative_to(bundle_root).as_posix(): path.read_text(encoding="utf-8")
                    for path in sorted(bundle_root.rglob("*"))
                    if path.is_file()
                }
                self.assertEqual(evaluator_input["bundle_files"], actual_files)
                self.assertFalse(forbidden_keys.intersection(all_keys(evaluator_input)))
                expected_inputs = [
                    {
                        "id": scenario["id"],
                        "scenario_sha256": hashlib.sha256(
                            canonical_json_bytes(scenario)
                        ).hexdigest(),
                        "stimulus": scenario["given"],
                    }
                    for scenario in scenarios_by_skill[skill_id]
                ]
                self.assertEqual(evaluator_input["scenarios"], expected_inputs)
                self.assertEqual(
                    evaluator_input["response_schema"],
                    {
                        "type": "object",
                        "required": ["responses"],
                        "response_fields": ["scenario_id", "raw_response"],
                    },
                )

    def test_sealed_skill_quality_evidence_contains_reviewed_raw_results(self):
        contract_path = self.evidence_root / "skill-quality-scenarios.json"
        contract = load_json(contract_path)
        report = load_json(self.evidence_root / "copilot-behavior.json")
        self.assertEqual(report["schema_version"], 2)
        self.assertEqual(report["runtime"], "copilot-cli")
        self.assertEqual(set(report["behavior_classes"]), REQUIRED_BEHAVIOR_CLASSES)
        self.assertEqual(
            report["scenario_contract_sha256"],
            hashlib.sha256(contract_path.read_bytes()).hexdigest(),
        )
        self.assertIsInstance(report["refinement_history"], list)
        self.assertTrue(report["limitations"])

        expected_bundles = {
            skill["id"]: validate_skill_bundle(
                self.catalog_root / skill["path"], skill["id"]
            )["digest"]
            for skill in self.catalog["skills"]
        }
        self.assertEqual(report["bundles"], expected_bundles)
        scenario_by_id = {scenario["id"]: scenario for scenario in contract["scenarios"]}
        self.assertEqual(
            {case["id"] for case in report["cases"]}, set(scenario_by_id)
        )
        for case in report["cases"]:
            scenario = scenario_by_id[case["id"]]
            with self.subTest(case=case["id"]):
                self.assertEqual(
                    set(case),
                    {
                        "id",
                        "skill",
                        "behavior_class",
                        "scenario_sha256",
                        "bundle_digest",
                        "attempt_id",
                        "prompt_version",
                        "evaluator_metadata",
                        "raw_response",
                        "observed_status",
                        "observed_actions",
                        "observed_required_observations",
                        "observed_forbidden",
                        "reviewer_decision",
                        "reviewed_by",
                        "reviewed_at",
                        "pass",
                    },
                )
                self.assertEqual(case["skill"], scenario["skill"])
                self.assertEqual(case["behavior_class"], scenario["behavior_class"])
                self.assertEqual(
                    case["scenario_sha256"],
                    hashlib.sha256(canonical_json_bytes(scenario)).hexdigest(),
                )
                self.assertEqual(case["bundle_digest"], expected_bundles[case["skill"]])
                self.assertEqual(case["prompt_version"], contract["prompt_version"])
                self.assertIsInstance(case["raw_response"], str)
                self.assertTrue(case["raw_response"].strip())
                self.assertEqual(case["observed_status"], scenario["expected_status"])
                self.assertIsInstance(case["observed_actions"], list)
                required_ids = {
                    observation["id"]
                    for observation in scenario["required_observations"]
                }
                self.assertEqual(
                    set(case["observed_required_observations"]), required_ids
                )
                self.assertEqual(case["observed_forbidden"], [])
                self.assertEqual(
                    set(case["evaluator_metadata"]),
                    {"model", "deployment", "model_version"},
                )
                for value in case["evaluator_metadata"].values():
                    self.assertTrue(value is None or (isinstance(value, str) and value))
                self.assertEqual(case["reviewer_decision"], "accepted")
                self.assertIsInstance(case["reviewed_by"], str)
                self.assertTrue(case["reviewed_by"].strip())
                self.assertIsInstance(case["reviewed_at"], str)
                self.assertTrue(case["reviewed_at"].strip())
                self.assertIs(case["pass"], True)
