"""End-to-end interview, authoring, registry, and packaged CLI acceptance."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from uuid import uuid4

from harness_factory import load_json
from web.acceptance.distribution_flow import (
    _console_environment,
    _hf,
    _login,
    _run_json,
)
from web.acceptance.postgres_flow import (
    AcceptanceFailure,
    _expect,
    _expect_status,
    _headers,
    _request,
    _wait_for_build,
    http_transport,
)
from web.api.config import Settings
from web.api.interviews.model import InterviewContext
from web.api.interviews.schemas import (
    DraftCandidate,
    InterviewReply,
    SuggestedEvidence,
)


class StructuredFakeInterviewModel:
    """Deterministic structured model used only by the default acceptance test."""

    def __init__(self, examples_root: Path) -> None:
        self.examples_root = examples_root
        self.question_calls = 0
        self.draft_calls = 0

    async def next_question(self, context: InterviewContext) -> InterviewReply:
        self.question_calls += 1
        if not context.turns:
            return InterviewReply(
                question="Which fictional SDLC handoff creates the most rework?",
                stage="discovery",
                evidence=[],
                proposed_scope=None,
                ready_for_review=False,
            )
        return InterviewReply(
            question="Is this the one fictional workflow scope to review?",
            stage="summary",
            evidence=[
                SuggestedEvidence(
                    id="temporary-model-evidence",
                    statement=(
                        "Fictional review criteria are clarified before implementation."
                    ),
                    kind="fact",
                    source_turn_ids=[context.turns[-1].id],
                )
            ],
            proposed_scope="issue-to-reviewed-pr",
            ready_for_review=True,
        )

    async def propose_design(
        self,
        context: InterviewContext,
        catalog: dict[str, object],
    ) -> DraftCandidate:
        del context, catalog
        self.draft_calls += 1
        profile = load_json(self.examples_root / "github-issue" / "profile.json")
        workflow = load_json(self.examples_root / "github-issue" / "workflow.json")
        scenarios = load_json(self.examples_root / "github-issue" / "scenarios.json")
        workflow.pop("approved")
        return DraftCandidate.model_validate(
            {
                "profile": profile,
                "workflow": workflow,
                "scenarios": scenarios,
            }
        )

    async def close(self) -> None:
        return None


def _author_headers(settings: Settings) -> dict[str, str]:
    return _headers(
        settings.development_organization_id,
        settings.development_subject_id,
        "author,reviewer,registry-admin,developer,org-admin",
    )


def run_interview_flow(
    *,
    settings: Settings,
    workspace: Path,
    hf_executable: str,
    base_url: str,
    examples_root: Path,
    python_executable: str = sys.executable,
    on_build_poll=None,
    require_postgres: bool = False,
) -> dict[str, object]:
    if require_postgres:
        _expect(
            settings.database_url.startswith("postgresql"),
            "interview acceptance requires PostgreSQL",
        )
    send = http_transport(base_url)
    headers = _author_headers(settings)
    other_headers = _headers("acceptance-other", "other-author", "author,developer")

    started = _expect_status(
        _request(
            send,
            "POST",
            "/api/interviews",
            headers=headers,
            body={
                "name": "Synthetic review interview",
                "customer_id": "synthetic-team",
                "consent_version": "2026-09-15",
                "consent_accepted": True,
                "request_id": str(uuid4()),
            },
        ),
        201,
        "start interview",
    )["session"]
    _expect(len(started["turns"]) == 1, "first interview question is missing")

    answered = _expect_status(
        _request(
            send,
            "POST",
            f"/api/interviews/{started['id']}/turns",
            headers=headers,
            body={
                "expected_revision": started["revision"],
                "request_id": str(uuid4()),
                "answer": (
                    "In this fictional team, unclear review criteria cause repeated "
                    "implementation rework."
                ),
            },
        ),
        200,
        "answer interview",
    )["session"]
    _expect(
        len(answered["proposed_evidence"]) == 1,
        "structured evidence proposal is missing",
    )
    resumed = _expect_status(
        _request(
            send,
            "GET",
            f"/api/interviews/{started['id']}",
            headers=headers,
        ),
        200,
        "resume interview",
    )["session"]
    _expect(resumed["revision"] == answered["revision"], "resume lost revision")
    _expect(
        _request(
            send,
            "GET",
            f"/api/interviews/{started['id']}",
            headers=other_headers,
        ).status
        == 404,
        "cross-tenant interview read was not hidden",
    )

    confirmed = _expect_status(
        _request(
            send,
            "POST",
            f"/api/interviews/{started['id']}/confirmations",
            headers=headers,
            body={
                "expected_revision": answered["revision"],
                "request_id": str(uuid4()),
                "decisions": [
                    {
                        "evidence_id": answered["proposed_evidence"][0]["id"],
                        "decision": "confirm",
                    }
                ],
            },
        ),
        200,
        "confirm evidence",
    )["session"]
    _expect(confirmed["scope"] is not None, "workflow scope was not proposed")
    _expect(len(confirmed["confirmed_evidence"]) == 1, "fact was not confirmed")

    proposal = _expect_status(
        _request(
            send,
            "POST",
            f"/api/interviews/{started['id']}/proposals",
            headers=headers,
            body={
                "expected_revision": confirmed["revision"],
                "request_id": str(uuid4()),
            },
        ),
        201,
        "generate proposal",
    )["proposal"]
    _expect("approved" not in proposal["workflow"], "model proposal forged approval")

    proposed_design = _expect_status(
        _request(
            send,
            "POST",
            f"/api/interviews/{started['id']}/apply",
            headers=headers,
            body={
                "expected_revision": proposal["revision"],
                "proposal_id": proposal["id"],
                "expected_proposal_digest": proposal["digest"],
                "confirm_scope": True,
                "design_id": None,
                "expected_design_digest": None,
            },
        ),
        200,
        "apply proposal",
    )["design"]
    _expect(proposed_design["status"] == "draft", "proposal did not create a draft")
    _expect(
        proposed_design["workflow"]["approved"]["by"]
        == settings.development_subject_id,
        "scope confirmation was not server-authored",
    )

    validated_design = _expect_status(
        _request(
            send,
            "POST",
            f"/api/designs/{proposed_design['id']}/validate",
            headers=headers,
        ),
        200,
        "validate design",
    )["design"]
    _expect(validated_design["status"] == "validated", "design was not validated")
    approved_design = _expect_status(
        _request(
            send,
            "POST",
            f"/api/designs/{proposed_design['id']}/reviews",
            headers=headers,
            body={
                "expected_digest": validated_design["digest"],
                "decision": "approved",
            },
        ),
        200,
        "review design",
    )["design"]

    queued = _expect_status(
        _request(
            send,
            "POST",
            f"/api/designs/{proposed_design['id']}/builds",
            headers=headers,
            body={"expected_digest": approved_design["digest"]},
        ),
        202,
        "queue build",
    )["build"]
    build = _wait_for_build(
        send,
        headers,
        queued["id"],
        60,
        on_build_poll,
    )

    slug = f"synthetic-interview-{uuid4().hex[:8]}"
    asset = _expect_status(
        _request(
            send,
            "POST",
            "/api/registry/assets",
            headers=headers,
            body={
                "type": "workflow",
                "slug": slug,
                "name": "Synthetic Interview Workflow",
                "description": "Acceptance-only fictional workflow.",
                "owner_subject_id": settings.development_subject_id,
            },
        ),
        201,
        "create registry asset",
    )["asset"]
    version = _expect_status(
        _request(
            send,
            "POST",
            f"/api/registry/assets/{asset['id']}/versions",
            headers=headers,
            body={
                "design_id": approved_design["id"],
                "design_digest": approved_design["digest"],
                "version": "1.0.0",
            },
        ),
        201,
        "create version",
    )["version"]
    reviewed_version = _expect_status(
        _request(
            send,
            "POST",
            f"/api/registry/versions/{version['id']}/reviews",
            headers=headers,
            body={"expected_digest": version["digest"], "decision": "approved"},
        ),
        200,
        "review version",
    )["version"]
    published = _expect_status(
        _request(
            send,
            "POST",
            f"/api/registry/versions/{version['id']}/publish",
            headers=headers,
            body={
                "expected_digest": reviewed_version["digest"],
                "channel": "stable",
            },
        ),
        200,
        "publish version",
    )["version"]

    workspace.mkdir(parents=True, exist_ok=False)
    console_cwd = workspace / "outside-checkout"
    console_cwd.mkdir()
    environment = _console_environment(workspace / "developer")
    _login(
        hf_executable,
        base_url=base_url,
        organization_id=settings.development_organization_id,
        subject_id="acceptance-developer",
        roles=("developer",),
        environment=environment,
        cwd=console_cwd,
    )
    reference = f"{slug}@1.0.0"
    search = _hf(
        hf_executable,
        ["search", slug],
        environment=environment,
        cwd=console_cwd,
    )
    _expect(search["result"][0]["slug"] == slug, "CLI search missed published asset")
    info = _hf(
        hf_executable,
        ["info", reference],
        environment=environment,
        cwd=console_cwd,
    )
    _expect(info["result"]["slug"] == slug, "CLI info returned wrong asset")

    target = workspace / "customer-repository"
    target.mkdir()
    customer_file = target / "customer-owned.txt"
    customer_file.write_text("preserve me\n", encoding="utf-8")
    preview = _hf(
        hf_executable,
        ["install", reference, "--target", str(target)],
        environment=environment,
        cwd=console_cwd,
    )["result"]
    installation = _hf(
        hf_executable,
        [
            "install",
            reference,
            "--target",
            str(target),
            "--approve",
            preview["digest"],
        ],
        environment=environment,
        cwd=console_cwd,
    )["result"]
    _expect(installation["operation"] == "install", "CLI apply did not install")
    _expect(
        customer_file.read_text(encoding="utf-8") == "preserve me\n",
        "CLI changed an unrelated customer file",
    )
    ready_result = _run_json(
        [
            python_executable,
            "-m",
            "harness_factory",
            "delivery-check",
            "--package",
            str(target),
        ],
        environment=environment,
        cwd=console_cwd,
    )
    _expect(ready_result["ready"] is False, "missing evaluation became ready")

    _expect_status(
        _request(
            send,
            "DELETE",
            f"/api/interviews/{started['id']}",
            headers=headers,
        ),
        200,
        "delete interview",
    )
    _expect(
        _request(
            send,
            "GET",
            f"/api/interviews/{started['id']}",
            headers=headers,
        ).status
        == 404,
        "deleted interview remained readable",
    )
    _expect_status(
        _request(
            send,
            "GET",
            f"/api/designs/{approved_design['id']}",
            headers=headers,
        ),
        200,
        "accepted design survives interview deletion",
    )
    _expect(
        _request(
            send,
            "GET",
            f"/api/designs/{approved_design['id']}",
            headers=other_headers,
        ).status
        == 404,
        "cross-tenant design read was not hidden",
    )

    return {
        "ok": True,
        "operation": "interview-acceptance",
        "database": (
            "postgresql"
            if settings.database_url.startswith("postgresql")
            else "sqlite"
        ),
        "proposed_design": proposed_design,
        "validated_design": validated_design,
        "published_version": published,
        "installation": installation,
        "ready_result": ready_result,
        "target": str(target),
        "interview_deleted": True,
        "cross_tenant": "not_found",
    }
