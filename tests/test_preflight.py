import subprocess
from unittest.mock import patch
from test_package import PackageCase

from harness_factory.preflight import preflight


class PreflightTests(PackageCase):
    def add_gh_system(self):
        self.profile["systems"].insert(
            0,
            {
                "id": "codehost",
                "kind": "source-control",
                "tool": "gh",
                "capabilities": ["read", "write"],
            },
        )

    def test_local_tracker_is_available_but_capabilities_are_unverified(self):
        self.generate()
        result = preflight(self.package, home=self.work / "home")
        self.assertEqual(result["issue_tracker"]["selected"], "local")
        self.assertEqual(result["issue_tracker"]["status"], "available")
        self.assertTrue(all(
            row["status"] == "unverified"
            for row in result["issue_tracker"]["capability_checks"]
        ))
        self.assertFalse(result["ready"])

    def test_skill_tracker_requires_the_selected_installed_skill(self):
        self.profile["issue_tracker"].update(
            provider="github",
            connection="skill",
            project="acme/widgets",
            path=None,
            skill="github-issues",
            mcp="mcp:github",
        )
        self.profile["systems"][0]["tool"] = "skill:github-issues"
        self.generate()
        skill = self.work / "home/.copilot/skills/github-issues/SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text(
            "---\nname: github-issues\ndescription: Manage GitHub issues.\n---\n"
        )

        available = preflight(self.package, home=self.work / "home")
        self.assertEqual(available["issue_tracker"]["status"], "available")
        self.assertEqual(available["items"][0]["status"], "available")
        self.assertTrue(all(
            row["status"] == "unverified"
            for row in available["issue_tracker"]["capability_checks"]
        ))
        self.assertFalse(available["ready"])

        skill.unlink()
        blocked = preflight(self.package, home=self.work / "home")
        self.assertEqual(blocked["issue_tracker"]["status"], "blocked")
        self.assertEqual(blocked["items"][0]["status"], "unverified")
        self.assertFalse(blocked["ready"])

    def test_mcp_tracker_remains_manual(self):
        self.profile["issue_tracker"].update(
            provider="jira",
            connection="mcp",
            project="PLAT",
            path=None,
            skill=None,
            mcp="mcp:jira",
        )
        self.profile["systems"][0]["tool"] = "mcp:jira"
        self.generate()
        result = preflight(self.package, home=self.work / "home")
        self.assertEqual(result["issue_tracker"]["selected"], "mcp")
        self.assertEqual(result["issue_tracker"]["status"], "manual")
        self.assertTrue(all(
            row["status"] == "manual"
            for row in result["issue_tracker"]["capability_checks"]
        ))
        self.assertFalse(result["ready"])

    def test_default_never_probes_and_reports_manual_unsupported(self):
        self.profile["systems"] += [
            {"id": "tickets", "kind": "issue", "tool": "mcp:tickets", "capabilities": ["read"]},
            {"id": "other", "kind": "issue", "tool": "custom", "capabilities": ["read"]},
        ]
        self.generate()
        with patch("shutil.which", return_value="/usr/bin/gh"), patch(
                "subprocess.run", side_effect=AssertionError("network probe forbidden")):
            result = preflight(self.package)
        self.assertEqual(result["operation"], "preflight")
        self.assertFalse(result["read_probes"])
        self.assertEqual([i["status"] for i in result["items"]],
                         ["available", "manual", "unverified"])
        self.assertFalse(result["ready"])

    def test_read_probes_bounded_and_sensitive_output_discarded(self):
        self.add_gh_system()
        self.generate()
        def run(args, **kwargs):
            self.assertIn(args, [["/usr/bin/gh", "auth", "status"], ["/usr/bin/gh", "api", "user"]])
            self.assertFalse(kwargs.get("shell", False))
            self.assertLessEqual(kwargs["timeout"], 15)
            self.assertEqual(kwargs["stdout"], subprocess.DEVNULL)
            self.assertEqual(kwargs["stderr"], subprocess.DEVNULL)
            return subprocess.CompletedProcess(args, 0)
        with patch("shutil.which", return_value="/usr/bin/gh"), patch("subprocess.run", side_effect=run):
            result = preflight(self.package, allow_read_probes=True)
        self.assertEqual(result["items"][0]["status"], "verified-read")
        self.assertNotIn("stdout", str(result))
        self.assertIn("authentication", result["items"][0])
        self.assertEqual(result["items"][0]["executable"]["status"], "available")
        self.assertEqual(result["items"][0]["authentication"]["status"], "verified-identity")
        self.assertEqual(result["items"][0]["authentication"]["scope"], "identity-only")
        self.assertEqual(result["items"][0]["capabilities"], [
            {"capability": "read", "status": "unverified"},
            {"capability": "write", "status": "unverified"},
        ])
        self.assertFalse(result["ready"])

    def test_default_reports_executable_identity_and_capabilities_separately(self):
        self.add_gh_system()
        self.generate()
        with patch("shutil.which", return_value="/usr/bin/gh"), patch(
                "subprocess.run", side_effect=AssertionError("default network call")):
            result = preflight(self.package)
        item = result["items"][0]
        self.assertIn("authentication", item)
        self.assertEqual(item["executable"]["status"], "available")
        self.assertEqual(item["authentication"]["status"], "unverified")
        self.assertTrue(all(capability["status"] == "unverified" for capability in item["capabilities"]))
        self.assertFalse(result["ready"])

    def test_timeout_and_missing_cli(self):
        self.add_gh_system()
        self.generate()
        with patch("shutil.which", return_value=None):
            self.assertEqual(preflight(self.package)["items"][0]["status"], "missing")
        with patch("shutil.which", return_value="/usr/bin/gh"), patch(
                "subprocess.run", side_effect=subprocess.TimeoutExpired("gh", 10)):
            self.assertEqual(preflight(self.package, True)["items"][0]["status"], "unverified")
