import json
import subprocess
import sys
from fixtures import FixtureCase


class CLITests(FixtureCase):
    def cli(self, *args):
        return subprocess.run([sys.executable, "-m", "harness_factory"] + list(args),
                              text=True, capture_output=True)

    def test_validate_success_json_and_failure_json(self):
        for name, data in [("profile", self.profile), ("workflow", self.workflow),
                           ("catalog", self.catalog)]:
            path = (self.root if name == "catalog" else self.work) / (name + ".json")
            path.write_text(json.dumps(data))
        args = ["validate", "--profile", str(self.work / "profile.json"),
                "--workflow", str(self.work / "workflow.json"), "--catalog", str(self.root / "catalog.json")]
        result = self.cli(*args)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"ok": True, "operation": "validate"})
        (self.work / "profile.json").write_text("{")
        result = self.cli(*args)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(json.loads(result.stderr)["ok"])
        self.assertNotIn("Traceback", result.stderr)

    def test_argparse_errors_are_json(self):
        result = self.cli("record", "--status", "invented")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(json.loads(result.stderr)["ok"])

    def test_generate_requires_scenarios(self):
        for name, data in [
            ("profile", self.profile),
            ("workflow", self.workflow),
            ("catalog", self.catalog),
        ]:
            ((self.root if name == "catalog" else self.work) / (name + ".json")).write_text(
                json.dumps(data)
            )
        result = self.cli(
            "generate",
            "--profile", str(self.work / "profile.json"),
            "--workflow", str(self.work / "workflow.json"),
            "--catalog", str(self.root / "catalog.json"),
            "--output", str(self.work / "package"),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--scenarios", json.loads(result.stderr)["error"])

    def test_tracker_guide_success_and_invalid_profile_are_json(self):
        profile_path = self.work / "profile.json"
        profile_path.write_text(json.dumps(self.profile))

        result = self.cli(
            "tracker-guide",
            "--profile",
            str(profile_path),
            "--target",
            str(self.work),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["operation"], "tracker-guide")

        self.profile["issue_tracker"]["path"] = "../outside"
        profile_path.write_text(json.dumps(self.profile))
        result = self.cli("tracker-guide", "--profile", str(profile_path))

        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(json.loads(result.stderr)["ok"])
        self.assertNotIn("Traceback", result.stderr)

    def test_complete_cli_delivery_and_evidence_without_factory_checkout(self):
        for name, data in [
            ("profile", self.profile),
            ("workflow", self.workflow),
            ("scenarios", self.scenarios),
            ("catalog", self.catalog),
        ]:
            ((self.root if name == "catalog" else self.work) / (name + ".json")).write_text(json.dumps(data))
        package, target = self.work / "package", self.work / "target"
        result = self.cli("generate", "--profile", str(self.work / "profile.json"),
                          "--workflow", str(self.work / "workflow.json"), "--catalog", str(self.root / "catalog.json"),
                          "--scenarios", str(self.work / "scenarios.json"),
                          "--output", str(package))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["operation"], "generate")
        manifest = package / ".harness/manifest.json"
        results = self.passing_results(__import__("hashlib").sha256(manifest.read_bytes()).hexdigest())
        results_path = self.work / "results.json"
        results_path.write_text(json.dumps(results))
        result = subprocess.run(
            [
                sys.executable, "-m", "harness_factory", "evaluate",
                "--package", ".", "--results", str(results_path),
            ],
            cwd=package,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            set(json.loads(result.stdout)),
            {"ok", "operation", "package", "workflow_id", "scenario_count", "receipt_sha256", "passed"},
        )
        results_path.write_text("{")
        result = subprocess.run(
            [
                sys.executable, "-m", "harness_factory", "evaluate",
                "--package", ".", "--results", str(results_path),
            ],
            cwd=package,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(json.loads(result.stderr)["ok"])
        self.assertNotIn("Traceback", result.stderr)
        results_path.write_text(json.dumps(results))
        result = self.cli("install", "--package", str(package), "--target", str(target))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(target.exists())
        digest = json.loads(result.stdout)["digest"]
        result = self.cli("install", "--package", str(package), "--target", str(target), "--approve", digest)
        self.assertEqual(result.returncode, 0, result.stderr)
        for args in [
            ["check", "--package", "."], ["preflight", "--package", "."],
            ["delivery-check", "--package", "."],
            ["record", "--package", ".", "--run", "one", "--step", "build", "--status", "running"],
            ["record", "--package", ".", "--run", "one", "--step", "build", "--status", "completed",
             "--evidence", "Observed tests passed; artifact change reviewed"],
            ["check", "--package", "."],
        ]:
            with self.subTest(command=args[0]):
                result = subprocess.run([sys.executable, "-m", "harness_factory"] + args, cwd=target,
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(json.loads(result.stdout)["ok"])
        result = subprocess.run(
            [
                sys.executable, "-m", "harness_factory", "evaluate",
                "--package", ".", "--results", str(results_path),
            ],
            cwd=target,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("distribution", json.loads(result.stderr)["error"])

    def test_delivery_check_missing_evaluation_is_success_but_corruption_is_not(self):
        for name, data in [
            ("profile", self.profile),
            ("workflow", self.workflow),
            ("scenarios", self.scenarios),
            ("catalog", self.catalog),
        ]:
            ((self.root if name == "catalog" else self.work) / (name + ".json")).write_text(
                json.dumps(data)
            )
        package = self.work / "delivery-package"
        generated = self.cli(
            "generate",
            "--profile", str(self.work / "profile.json"),
            "--workflow", str(self.work / "workflow.json"),
            "--scenarios", str(self.work / "scenarios.json"),
            "--catalog", str(self.root / "catalog.json"),
            "--output", str(package),
        )
        self.assertEqual(generated.returncode, 0, generated.stderr)

        result = self.cli("delivery-check", "--package", str(package))
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["ready"])
        self.assertEqual(payload["customer_evaluation"]["status"], "missing")

        managed = package / ".agents/skills/worker/SKILL.md"
        managed.write_text(managed.read_text() + "\nCorrupted.\n")
        result = self.cli("delivery-check", "--package", str(package))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stderr)["type"], "PackageError")
