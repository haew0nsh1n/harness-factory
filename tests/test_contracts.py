import copy
import json
import os
from pathlib import Path
from fixtures import FixtureCase

from harness_factory.contracts import load_json, validate
from harness_factory.errors import ValidationError


class ContractTests(FixtureCase):
    def check(self):
        return validate(self.profile, self.workflow, self.catalog, self.root)

    def test_valid_contract(self):
        self.assertIsNone(self.check())

    def test_issue_tracker_accepts_markdown_skill_and_mcp_connections(self):
        self.check()

        self.profile["issue_tracker"].update(
            provider="github", connection="skill", path=None,
            skill="github-issues", mcp="mcp:github",
            project="acme/widgets",
        )
        self.profile["systems"][0]["tool"] = "skill:github-issues"
        self.check()

        self.profile["issue_tracker"].update(
            provider="jira", connection="mcp", path=None,
            skill=None, mcp="mcp:jira", project="PLAT",
        )
        self.profile["systems"][0]["tool"] = "mcp:jira"
        self.check()

    def test_issue_tracker_rejects_invalid_combinations_and_paths(self):
        original_profile = copy.deepcopy(self.profile)
        cases = [
            ({"provider": "other"}, "provider"),
            ({"connection": "auto"}, "connection"),
            ({"path": "../outside"}, "path"),
            ({"provider": "github", "connection": "local", "path": None}, "connection"),
            ({"connection": "skill", "skill": "../bad", "path": None}, "skill"),
            ({"connection": "mcp", "mcp": "mcp:jira;env", "path": None}, "mcp"),
            ({"system_id": "missing"}, "system_id"),
            ({"capabilities": ["admin"]}, "capabilities"),
        ]
        for mutation, field in cases:
            self.profile = copy.deepcopy(original_profile)
            if mutation.get("connection") == "skill":
                self.profile["issue_tracker"].update(
                    provider="github", connection="skill", path=None,
                    skill="github-issues", mcp="mcp:github",
                    project="acme/widgets",
                )
                self.profile["systems"][0]["tool"] = "skill:github-issues"
            elif mutation.get("connection") == "mcp":
                self.profile["issue_tracker"].update(
                    provider="github", connection="mcp", path=None,
                    skill=None, mcp="mcp:github", project="acme/widgets",
                )
                self.profile["systems"][0]["tool"] = "mcp:github"
            elif mutation.get("provider") == "github":
                self.profile["issue_tracker"]["project"] = "acme/widgets"
            self.profile["issue_tracker"].update(mutation)
            with self.subTest(mutation=mutation), self.assertRaisesRegex(ValidationError, field):
                self.check()

    def test_required_profile_fields_and_unknown_fields(self):
        original = copy.deepcopy(self.profile)
        for key in original:
            with self.subTest(key=key):
                self.profile = copy.deepcopy(original)
                del self.profile[key]
                with self.assertRaisesRegex(ValidationError, key):
                    self.check()
        self.profile = original
        self.profile["typo"] = True
        with self.assertRaisesRegex(ValidationError, "typo"):
            self.check()

    def test_external_write_requires_approval(self):
        self.workflow["steps"][0].update(effect="external-write", approval=False)
        with self.assertRaisesRegex(ValidationError, "approval"):
            self.check()

    def test_issue_tracker_write_requires_approved_external_write_or_manual_handoff(self):
        self.profile["issue_tracker"].update(
            provider="github",
            connection="mcp",
            project="acme/widgets",
            path=None,
            skill=None,
            mcp="mcp:github",
        )
        self.profile["systems"][0]["tool"] = "mcp:github"
        self.workflow["steps"][0].update(
            tools=["github.issue-create"], effect="external-write", approval=False,
        )
        with self.assertRaisesRegex(ValidationError, "tracker write"):
            self.check()

    def test_markdown_tracker_write_allows_approved_local_step(self):
        self.workflow["steps"][0].update(
            skill="hf-issues-markdown",
            tools=["github.issue-create"],
            effect="local",
            approval=True,
            approver="owner",
        )
        self.check()

    def test_markdown_path_validation_is_independent_of_process_directory(self):
        cwd = self.work / "cwd"
        cwd.mkdir()
        (cwd / "issues").symlink_to(self.work / "outside", target_is_directory=True)
        previous = Path.cwd()
        try:
            os.chdir(str(cwd))
            self.check()
        finally:
            os.chdir(str(previous))

    def test_issue_tracker_rejects_unsafe_provider_project_identifiers(self):
        original = copy.deepcopy(self.profile)
        cases = [
            ("markdown", "https://user:pass@example.com/repository"),
            ("markdown", "project\nsecret"),
            ("github", "owner"),
            ("github", "user:pass@example.com/repository"),
            ("jira", "https://jira.example.com/browse/PLAT"),
            ("jira", "PLAT\nTOKEN"),
        ]
        for provider, project in cases:
            self.profile = copy.deepcopy(original)
            if provider == "github":
                self.profile["issue_tracker"].update(
                    provider="github",
                    connection="mcp",
                    project=project,
                    path=None,
                    skill=None,
                    mcp="mcp:github",
                )
                self.profile["systems"][0]["tool"] = "mcp:github"
            elif provider == "jira":
                self.profile["issue_tracker"].update(
                    provider="jira",
                    connection="mcp",
                    project=project,
                    path=None,
                    skill=None,
                    mcp="mcp:jira",
                )
                self.profile["systems"][0]["tool"] = "mcp:jira"
            else:
                self.profile["issue_tracker"]["project"] = project
            with self.subTest(provider=provider, project=project), self.assertRaisesRegex(
                ValidationError, "project"
            ):
                self.check()

    def test_issue_tracker_rejects_workflow_capability_not_selected_by_contract(self):
        self.profile["systems"][0]["capabilities"].append("issue-comment")
        self.workflow["steps"][0]["tools"] = ["github.issue-comment"]
        with self.assertRaisesRegex(ValidationError, "issue_tracker.capabilities"):
            self.check()

    def test_issue_tracker_allows_non_tracker_capability_on_linked_system(self):
        self.profile["systems"][0]["capabilities"].append("pr-read")
        self.workflow["steps"][0]["tools"] = ["github.pr-read"]
        self.check()

    def test_local_tracker_requires_verified_markdown_skill_evidence(self):
        markdown = self.catalog["skills"][1]
        markdown["compatibility"]["status"] = "unverified"
        with self.assertRaisesRegex(ValidationError, "selected skill must be verified"):
            self.check()

    def test_cycle(self):
        self.workflow["steps"][0]["needs"] = ["build"]
        with self.assertRaisesRegex(ValidationError, "cycle"):
            self.check()

    def test_ancestor_inputs_not_sibling(self):
        self.workflow["steps"].append(self.step(id="second", inputs=["change"], outputs=["final"]))
        with self.assertRaisesRegex(ValidationError, "inputs"):
            self.check()
        self.workflow["steps"][1]["needs"] = ["build"]
        self.check()

    def test_unknown_tool_requires_manual(self):
        self.workflow["steps"][0]["tools"] = ["missing.read"]
        with self.assertRaisesRegex(ValidationError, "tools"):
            self.check()
        self.workflow["steps"][0].update(
            effect="manual", manual={"owner": "owner", "instructions": "Read manually",
                                     "resume_when": "Evidence reviewed"})
        self.check()

    def test_manual_contract(self):
        self.workflow["steps"][0]["effect"] = "manual"
        with self.assertRaisesRegex(ValidationError, "manual"):
            self.check()

    def test_malformed_json_duplicate_keys_and_nonobject(self):
        for payload in ["{", "[]", '{"a": 1, "a": 2}', '{"a": NaN}']:
            (self.work / "bad.json").write_text(payload)
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                load_json(self.work / "bad.json")
        with self.assertRaises(ValidationError):
            load_json(self.work / "missing.json")

    def test_bad_metadata_approval_effect_and_capability(self):
        original = copy.deepcopy(self.catalog)
        for section, key, value in [
            ("source", "revision", "main"), ("source", "license", ""),
            ("compatibility", "status", "candidate"),
            ("compatibility", "evidence", "absent.txt")]:
            with self.subTest(key=key):
                self.catalog = copy.deepcopy(original)
                self.catalog["skills"][0][section][key] = value
                with self.assertRaises(ValidationError):
                    self.check()
        self.catalog = original
        self.catalog["skills"][0]["effects"] = ["read"]
        with self.assertRaisesRegex(ValidationError, "effect"):
            self.check()
        self.catalog["skills"][0]["effects"] = ["local"]
        self.catalog["skills"][0]["requires"] = ["github.write"]
        with self.assertRaisesRegex(ValidationError, "requires"):
            self.check()

    def test_bad_ids_types_artifacts_and_customer(self):
        original = copy.deepcopy(self.workflow)
        for field, value in [("schema_version", True), ("customer_id", "other"),
                             ("approved", None), ("inputs", ["../issue"]),
                             ("outputs", ["missing"]), ("steps", [])]:
            self.workflow = copy.deepcopy(original)
            self.workflow[field] = value
            with self.subTest(field=field), self.assertRaises(ValidationError):
                self.check()
        self.workflow = original
        self.workflow["steps"].append(copy.deepcopy(self.workflow["steps"][0]))
        with self.assertRaisesRegex(ValidationError, "duplicate"):
            self.check()

    def test_catalog_paths_and_symlinks(self):
        skill = self.catalog["skills"][0]
        for path in ["../outside", "/outside", "skills/../skills/worker"]:
            skill["path"] = path
            with self.subTest(path=path), self.assertRaises(ValidationError):
                self.check()
        skill["path"] = "skills/link"
        (self.root / "skills/link").symlink_to(self.root / "skills/worker", target_is_directory=True)
        with self.assertRaisesRegex(ValidationError, "symlink"):
            self.check()

    def test_system_tool_is_token_not_command(self):
        self.profile["systems"][0]["tool"] = "gh api user; echo secret"
        with self.assertRaisesRegex(ValidationError, "tool"):
            self.check()

    def test_empty_approver_allowed_only_without_gate(self):
        self.workflow["steps"][0]["approver"] = ""
        self.check()
        self.workflow["steps"][0]["approval"] = True
        with self.assertRaisesRegex(ValidationError, "approver"):
            self.check()

    def test_malformed_status_runtime_empty_files_and_source_path(self):
        original = copy.deepcopy(self.catalog)
        for section, key, value in [
            ("compatibility", "status", []), ("compatibility", "runtime", "other-host"),
            ("source", "path", "../escape"), ("source", "path", "/absolute")]:
            self.catalog = copy.deepcopy(original)
            self.catalog["skills"][0][section][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValidationError):
                self.check()
        self.catalog = original
        (self.root / "license.txt").write_text("")
        with self.assertRaisesRegex(ValidationError, "license"):
            self.check()

    def test_json_symlink_is_rejected(self):
        (self.work / "real.json").write_text("{}")
        (self.work / "linked.json").symlink_to(self.work / "real.json")
        with self.assertRaisesRegex(ValidationError, "symlink"):
            load_json(self.work / "linked.json")

    def test_approval_timestamp_is_timezone_aware_iso_datetime(self):
        for value in ["yesterday", "2026-09-10", "2026-09-10T00:00:00"]:
            self.workflow["approved"]["at"] = value
            with self.subTest(value=value), self.assertRaisesRegex(ValidationError, "approved.at"):
                self.check()

    def test_skill_entry_must_have_usable_frontmatter(self):
        (self.root / "skills/worker/SKILL.md").write_text("")
        with self.assertRaisesRegex(ValidationError, "SKILL"):
            self.check()

    def test_wrong_json_field_types_never_escape_as_programming_errors(self):
        original = copy.deepcopy((self.profile, self.workflow, self.catalog))
        for root_index, fields in enumerate(original):
            for key in fields:
                for value in (None, [], {}, 3, True, ""):
                    self.profile, self.workflow, self.catalog = copy.deepcopy(original)
                    (self.profile, self.workflow, self.catalog)[root_index][key] = value
                    with self.subTest(root=root_index, key=key, value=value):
                        try:
                            self.check()
                        except ValidationError:
                            pass

    def test_source_url_does_not_embed_credentials(self):
        for url in ["https://user:secret@example.com/source", "https://[", "https:///missing-host"]:
            self.catalog["skills"][0]["source"]["url"] = url
            with self.subTest(url=url), self.assertRaisesRegex(ValidationError, "url"):
                self.check()

    def test_skill_edit_invalidates_behavior_evidence(self):
        entry = self.root / "skills/worker/SKILL.md"
        entry.write_text(entry.read_text() + "\nChanged behavior after approval.\n")
        with self.assertRaisesRegex(ValidationError, "evidence.*hash"):
            self.check()

    def test_selected_evidence_requires_correct_hash_and_passing_cases(self):
        original = copy.deepcopy(self.evidence)
        for field, value in [
            ("schema_version", True), ("runtime", "other-host"),
            ("skills", {}), ("skills", {"worker": "0" * 64}),
            ("skills", {"worker": "not-a-hash"}),
            ("cases", []), ("cases", [{"pass": False}]),
            ("cases", [{"pass": 1}]), ("cases", [{}]), ("cases", "passed"),
        ]:
            evidence = copy.deepcopy(original)
            evidence[field] = value
            (self.root / "evidence.json").write_text(json.dumps(evidence))
            with self.subTest(field=field, value=value), self.assertRaisesRegex(ValidationError, "evidence"):
                self.check()

    def test_evidence_prose_metadata_is_optional(self):
        evidence = {key: self.evidence[key] for key in ("schema_version", "runtime", "skills", "cases")}
        (self.root / "evidence.json").write_text(json.dumps(evidence))
        self.check()

    def test_optional_after_approval_only_for_gated_read_or_local_steps(self):
        step = self.workflow["steps"][0]
        step.update(approval=True, approver="owner", approval_timing="after")
        for effect in ("read", "local"):
            step["effect"] = effect
            self.check()
        for effect in ("external-write", "manual"):
            step["effect"] = effect
            with self.subTest(effect=effect), self.assertRaisesRegex(ValidationError, "approval_timing"):
                self.check()
        step["effect"] = "local"
        step.update(approval=False, approver=None)
        with self.assertRaisesRegex(ValidationError, "approval_timing"):
            self.check()
        step.update(approval=True, approver="owner")
        for timing in ("later", None, True, []):
            step["approval_timing"] = timing
            with self.subTest(timing=timing), self.assertRaisesRegex(ValidationError, "approval_timing"):
                self.check()

    def test_missing_skill_reference_rejected_even_with_matching_evaluation_hash(self):
        self.write_skill_body("[required](references/missing.md)\n")
        with self.assertRaisesRegex(ValidationError, "reference.*missing"):
            self.check()

    def test_local_markdown_links_and_images_are_self_contained(self):
        skill = self.root / "skills/worker"
        (skill / "references").mkdir()
        (skill / "references/guide.md").write_text("[Back](../SKILL.md)\n![Diagram](diagram.png)\n")
        (skill / "references/diagram.png").write_bytes(b"fixture-image")
        self.write_skill_body(
            "[Guide](references/guide.md#details)\n[External](https://example.com/not-local)\n"
            "[Anchor](#details)\n[Named][guide]\n[guide]: <references/guide.md> \"Guide\"\n"
            "`[not a link](references/absent.md)`\n```\n[example](absent.md)\n```\n")
        self.check()
        (skill / "references/diagram.png").unlink()
        with self.assertRaisesRegex(ValidationError, "reference.*diagram"):
            self.check()

    def test_markdown_reference_escape_and_symlink_rejected(self):
        for link in ("../../license.txt", "/outside", "%2e%2e/%2e%2e/license.txt", "file:///outside"):
            self.write_skill_body("[Resource](" + link + ")\n")
            with self.subTest(link=link), self.assertRaisesRegex(ValidationError, "reference"):
                self.check()
        (self.root / "skills/worker/linked.md").symlink_to(self.root / "license.txt")
        self.write_skill_body("[Resource](linked.md)\n")
        with self.assertRaisesRegex(ValidationError, "symlink"):
            self.check()

    def test_undefined_reference_style_link_is_rejected(self):
        self.write_skill_body("![Required image][missing]\n")
        with self.assertRaisesRegex(ValidationError, "reference"):
            self.check()
