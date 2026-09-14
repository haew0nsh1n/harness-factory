import shutil
import uuid
import hashlib
import json
from pathlib import Path
from unittest import TestCase


class FixtureCase(TestCase):
    def setUp(self):
        self.work = Path(__file__).resolve().parent / (".case-" + uuid.uuid4().hex)
        self.work.mkdir()
        self.addCleanup(shutil.rmtree, self.work)
        self.root = self.work / "catalog"
        (self.root / "skills/worker").mkdir(parents=True)
        (self.root / "skills/worker/SKILL.md").write_text(
            "---\nname: worker\ndescription: Work carefully.\n---\nProduce evidence.\n"
        )
        (self.root / "skills/hf-issues-markdown").mkdir(parents=True)
        (self.root / "skills/hf-issues-markdown/SKILL.md").write_text(
            "---\nname: hf-issues-markdown\ndescription: Manage local issue files.\n---\n"
            "Create one Markdown file per issue. Do not commit or push.\n"
        )
        (self.root / "license.txt").write_text("MIT\nCopyright Example\n")
        self.evidence = {
            "schema_version": 1, "runtime": "copilot-cli", "date": "2026-09-10",
            "method": "Read-only synthetic agent evaluation", "scope": "Bounded simulation only",
            "skills": {
                "worker": hashlib.sha256(
                    (self.root / "skills/worker/SKILL.md").read_bytes()
                ).hexdigest(),
                "hf-issues-markdown": hashlib.sha256(
                    (self.root / "skills/hf-issues-markdown/SKILL.md").read_bytes()
                ).hexdigest(),
            },
            "cases": [{"id": "normal", "status": "completed", "observed": "Expected synthetic handoff", "pass": True}],
        }
        (self.root / "evidence.json").write_text(json.dumps(self.evidence))
        self.profile = {
            "schema_version": 1, "customer_id": "acme", "name": "Acme",
            "sdlc": [{"stage": "build", "current": "manual", "desired": "reviewed"}],
            "glossary": {"PR": "pull request"},
            "systems": [{
                "id": "github",
                "kind": "issue-tracker",
                "tool": "git",
                "capabilities": ["issue-read", "issue-create", "issue-update"],
            }],
            "issue_tracker": {
                "system_id": "github",
                "provider": "markdown",
                "connection": "local",
                "project": "acme",
                "path": "issues",
                "skill": None,
                "mcp": None,
                "capabilities": ["issue-read", "issue-create", "issue-update"],
            },
            "roles": ["owner"], "pains": [{"description": "private pain",
                                          "impact": "delay", "frequency": "daily"}],
            "success_criteria": ["reviewed change"], "constraints": [],
            "facts": [{"id": "fact", "statement": "private fact", "evidence": "private evidence"}],
            "assumptions": [], "unknowns": [],
        }
        self.workflow = {
            "schema_version": 1, "id": "issue-flow", "name": "Issue flow",
            "customer_id": "acme", "goal": "review change", "trigger": "issue assigned",
            "inputs": ["issue"], "outputs": ["change"], "customer_rules": ["Review before publication"],
            "approved": {"by": "owner", "at": "2026-09-10T00:00:00Z"},
            "steps": [self.step()], "traceability": [
                {"requirement": "reviewed change", "steps": ["build"], "checks": ["Review evidence"]}
            ],
        }
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
        self.catalog = {"schema_version": 1, "skills": [
            {
                "id": "worker", "path": "skills/worker", "description": "Work",
                "inputs": ["issue"], "outputs": ["change"], "requires": [],
                "effects": ["read", "local", "external-write", "manual"],
                "source": {"url": "https://example.com/worker", "revision": "a" * 40,
                           "path": "skills/worker", "license": "MIT", "license_file": "license.txt"},
                "compatibility": {"runtime": "copilot-cli", "status": "verified", "evidence": "evidence.json"},
            },
            {
                "id": "hf-issues-markdown",
                "path": "skills/hf-issues-markdown",
                "description": "Manage local issue files",
                "inputs": ["issue-request"],
                "outputs": ["issue-file"],
                "requires": [],
                "effects": ["read", "local"],
                "source": {
                    "url": "https://example.com/issues",
                    "revision": "b" * 40,
                    "path": "skills/hf-issues-markdown",
                    "license": "MIT",
                    "license_file": "license.txt",
                },
                "compatibility": {
                    "runtime": "copilot-cli",
                    "status": "verified",
                    "evidence": "evidence.json",
                },
            },
        ]}

    def passing_results(self, manifest_sha256):
        return {
            "schema_version": 1,
            "workflow": self.workflow["id"],
            "package_manifest_sha256": manifest_sha256,
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

    def step(self, **overrides):
        step = {"id": "build", "name": "Build", "skill": "worker", "needs": [],
                "inputs": ["issue"], "outputs": ["change"], "tools": ["github.issue-read"],
                "effect": "local", "approval": False, "approver": None,
                "completion": "Reviewed artifact exists", "failure": "Stop and report",
                "manual": None}
        step.update(overrides)
        return step

    def write_skill_body(self, body):
        path = self.root / "skills/worker/SKILL.md"
        path.write_text("---\nname: worker\ndescription: Work carefully.\n---\n" + body)
        self.evidence["skills"]["worker"] = hashlib.sha256(path.read_bytes()).hexdigest()
        (self.root / "evidence.json").write_text(json.dumps(self.evidence))
