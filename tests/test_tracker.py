import copy

from fixtures import FixtureCase

from harness_factory.tracker import tracker_guide


class TrackerGuideTests(FixtureCase):
    def skill_profile(self):
        profile = copy.deepcopy(self.profile)
        profile["issue_tracker"].update(
            provider="github",
            connection="skill",
            path=None,
            skill="github-issues",
            mcp="mcp:github",
            project="acme/widgets",
        )
        profile["systems"][0]["tool"] = "skill:github-issues"
        return profile

    def mcp_profile(self):
        profile = copy.deepcopy(self.profile)
        profile["issue_tracker"].update(
            provider="jira",
            connection="mcp",
            path=None,
            skill=None,
            mcp="mcp:jira",
            project="PLAT",
        )
        profile["systems"][0]["tool"] = "mcp:jira"
        return profile

    def write_skill(self, root, body=None):
        skill_file = root / ".agents/skills/github-issues/SKILL.md"
        skill_file.parent.mkdir(parents=True)
        skill_file.write_text(
            body
            or "---\nname: github-issues\ndescription: Manage GitHub issues.\n---\nUse approved APIs.\n"
        )
        return skill_file

    def test_markdown_guide_is_local_and_names_issue_path(self):
        result = tracker_guide(self.profile, self.work)

        self.assertEqual(result["selected"], "local")
        self.assertEqual(result["provider"], "markdown")
        self.assertEqual(result["issue_path"], str(self.work / "issues"))
        self.assertEqual(result["status"], "available")
        self.assertTrue(any("hf-issues-markdown" in step for step in result["steps"]))

    def test_skill_guide_discovers_project_skill_without_exposing_body(self):
        skill_file = self.write_skill(self.work)

        result = tracker_guide(
            self.skill_profile(), self.work, home=self.work / "home"
        )

        self.assertEqual(result["selected"], "skill")
        self.assertEqual(result["status"], "available")
        self.assertEqual(
            result["skill"],
            {"name": "github-issues", "location": str(skill_file)},
        )
        self.assertTrue(
            all(item["status"] == "unverified" for item in result["capability_checks"])
        )
        self.assertNotIn("Use approved APIs.", str(result))

    def test_project_skill_takes_precedence_over_home_skill(self):
        project_skill = self.write_skill(self.work)
        home = self.work / "home"
        self.write_skill(home)

        result = tracker_guide(self.skill_profile(), self.work, home=home)

        self.assertEqual(result["skill"]["location"], str(project_skill))

    def test_symlinked_skill_is_blocked(self):
        real_skill = self.write_skill(self.work / "elsewhere")
        candidate = self.work / ".agents/skills/github-issues/SKILL.md"
        candidate.parent.mkdir(parents=True)
        candidate.symlink_to(real_skill)

        result = tracker_guide(
            self.skill_profile(), self.work, home=self.work / "home"
        )

        self.assertEqual(result["status"], "blocked")
        self.assertNotIn("skill", result)
        self.assertTrue(any("symlink" in step.lower() for step in result["steps"]))

    def test_invalid_project_skill_is_skipped_for_valid_home_skill(self):
        real_skill = self.write_skill(self.work / "elsewhere")
        candidate = self.work / ".agents/skills/github-issues/SKILL.md"
        candidate.parent.mkdir(parents=True)
        candidate.symlink_to(real_skill)
        home = self.work / "home"
        home_skill = self.write_skill(home)

        result = tracker_guide(self.skill_profile(), self.work, home=home)

        self.assertEqual(result["status"], "available")
        self.assertEqual(result["skill"]["location"], str(home_skill))

    def test_symlinked_project_target_is_blocked(self):
        real_target = self.work / "real-project"
        self.write_skill(real_target)
        target = self.work / "project-link"
        target.symlink_to(real_target, target_is_directory=True)

        result = tracker_guide(
            self.skill_profile(), target, home=self.work / "home"
        )

        self.assertEqual(result["status"], "blocked")
        self.assertNotIn("skill", result)
        self.assertTrue(any("symlink" in step.lower() for step in result["steps"]))

    def test_project_target_with_symlinked_ancestor_is_blocked(self):
        real_parent = self.work / "real-parent"
        self.write_skill(real_parent / "project")
        linked_parent = self.work / "linked-parent"
        linked_parent.symlink_to(real_parent, target_is_directory=True)

        result = tracker_guide(
            self.skill_profile(),
            linked_parent / "project",
            home=self.work / "home",
        )

        self.assertEqual(result["status"], "blocked")
        self.assertNotIn("skill", result)
        self.assertTrue(any("symlink" in step.lower() for step in result["steps"]))

    def test_markdown_issue_path_with_symlinked_component_is_blocked(self):
        real_issues = self.work / "real-issues"
        real_issues.mkdir()
        (self.work / "issues").symlink_to(real_issues, target_is_directory=True)

        result = tracker_guide(self.profile, self.work)

        self.assertEqual(result["status"], "blocked")
        self.assertTrue(any("symlink" in step.lower() for step in result["steps"]))

    def test_malformed_skill_frontmatter_is_blocked(self):
        self.write_skill(self.work, "name: github-issues\nNo frontmatter.\n")

        result = tracker_guide(
            self.skill_profile(), self.work, home=self.work / "home"
        )

        self.assertEqual(result["status"], "blocked")
        self.assertTrue(
            any("frontmatter" in step.lower() for step in result["steps"])
        )

    def test_missing_skill_recommends_regenerating_for_mcp(self):
        result = tracker_guide(
            self.skill_profile(), self.work, home=self.work / "home"
        )

        self.assertEqual(result["status"], "blocked")
        self.assertTrue(
            any(
                "regenerate" in step.lower() and "mcp:github" in step
                for step in result["steps"]
            )
        )

    def test_mcp_guide_requires_manual_configuration_and_verification(self):
        result = tracker_guide(self.mcp_profile(), self.work)

        self.assertEqual(result["selected"], "mcp")
        self.assertEqual(result["status"], "manual")
        self.assertTrue(any("/mcp" in step for step in result["steps"]))
        self.assertTrue(
            all(item["status"] == "manual" for item in result["capability_checks"])
        )
        self.assertNotIn("endpoint", result)
        self.assertNotIn("credentials", result)
        self.assertEqual(
            result["steps"],
            [
                "Open Copilot /mcp and configure the customer-approved jira server.",
                "Authenticate through the approved native mechanism; do not store credentials in the profile or package.",
                "Verify each declared capability against the selected project before workflow execution.",
            ],
        )
