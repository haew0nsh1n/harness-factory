from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from web.api.validation import require_sha256_digest


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


Stage = Literal[
    "discovery",
    "planning",
    "implementation",
    "testing",
    "review",
    "release",
    "operations",
    "summary",
]


class StartInterviewRequest(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    customer_id: str = Field(
        min_length=1, max_length=80, pattern=r"^[a-z0-9](?:[a-z0-9-]{0,78}[a-z0-9])?$"
    )
    consent_version: Literal["2026-09-15"]
    consent_accepted: Literal[True]
    request_id: UUID = Field(strict=False)


class AnswerRequest(StrictModel):
    expected_revision: int = Field(ge=0)
    request_id: UUID = Field(strict=False)
    answer: str = Field(min_length=1, max_length=8000)


class EvidenceDecision(StrictModel):
    evidence_id: UUID = Field(strict=False)
    decision: Literal["confirm", "reject"]


class ConfirmationRequest(StrictModel):
    expected_revision: int = Field(ge=0)
    request_id: UUID = Field(strict=False)
    decisions: list[EvidenceDecision] = Field(min_length=1, max_length=50)

    @field_validator("decisions")
    @classmethod
    def require_unique_evidence_ids(
        cls, decisions: list[EvidenceDecision]
    ) -> list[EvidenceDecision]:
        ids = [decision.evidence_id for decision in decisions]
        if len(ids) != len(set(ids)):
            raise ValueError("evidence decisions must be unique")
        return decisions


class ProposalRequest(StrictModel):
    expected_revision: int = Field(ge=0)
    request_id: UUID = Field(strict=False)


class ApplyProposalRequest(StrictModel):
    expected_revision: int = Field(ge=0)
    proposal_id: UUID = Field(strict=False)
    expected_proposal_digest: str = Field(min_length=64, max_length=64)
    confirm_scope: Literal[True]
    design_id: UUID | None = Field(default=None, strict=False)
    expected_design_digest: str | None = Field(
        default=None, min_length=64, max_length=64
    )

    @field_validator("expected_proposal_digest", "expected_design_digest")
    @classmethod
    def validate_digest(cls, value: str | None, info) -> str | None:
        if value is None:
            return None
        return require_sha256_digest(value, info.field_name)

    @model_validator(mode="after")
    def require_target_digest(self) -> "ApplyProposalRequest":
        if (self.design_id is None) != (self.expected_design_digest is None):
            raise ValueError(
                "design_id and expected_design_digest must be supplied together"
            )
        return self


class InterviewTurnResponse(StrictModel):
    id: str
    role: Literal["user", "assistant"]
    text: str
    sequence: int
    created_at: datetime


class EvidenceResponse(StrictModel):
    id: str
    statement: str
    kind: Literal["fact", "assumption", "unknown"]
    source_turn_ids: list[str]


class InterviewProposalResponse(StrictModel):
    id: str
    revision: int
    digest: str
    status: str
    findings: list[dict[str, str]]
    created_at: datetime
    updated_at: datetime


class InterviewProposalDetailResponse(InterviewProposalResponse):
    profile: dict[str, object]
    workflow: dict[str, object]
    scenarios: dict[str, object]
    catalog: dict[str, object]


class InterviewOperationResponse(StrictModel):
    request_id: str
    kind: str
    status: str


class InterviewSessionResponse(StrictModel):
    id: str
    organization_id: str
    owner_subject_id: str
    name: str
    customer_id: str
    revision: int
    status: Literal["active", "awaiting-confirmation", "completed"]
    consent_version: str
    consented_at: datetime
    stage: Stage
    scope: str | None
    proposed_evidence: list[EvidenceResponse]
    confirmed_evidence: list[EvidenceResponse]
    turns: list[InterviewTurnResponse]
    proposals: list[InterviewProposalResponse]
    last_operation: InterviewOperationResponse | None
    last_error_code: str | None
    created_at: datetime
    updated_at: datetime
    expires_at: datetime

class SuggestedEvidence(StrictModel):
    id: str = Field(min_length=1, max_length=128)
    statement: str = Field(min_length=1, max_length=4000)
    kind: Literal["fact", "assumption", "unknown"]
    source_turn_ids: list[str] = Field(max_length=60)


class InterviewReply(StrictModel):
    question: str = Field(min_length=1, max_length=2000)
    stage: Stage
    evidence: list[SuggestedEvidence] = Field(max_length=50)
    proposed_scope: str | None = Field(default=None, max_length=256)
    ready_for_review: bool

    @field_validator("question")
    @classmethod
    def require_one_question(cls, value: str) -> str:
        if value.count("?") > 1:
            raise ValueError("question must contain at most one question")
        return value


class SdlcStage(StrictModel):
    stage: str = Field(min_length=1)
    current: str = Field(min_length=1)
    desired: str = Field(min_length=1)


class DeclaredSystem(StrictModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    kind: str = Field(min_length=1)
    tool: str = Field(min_length=1)
    capabilities: list[str] = Field(min_length=1)


class IssueTracker(StrictModel):
    system_id: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    provider: Literal["markdown", "github", "jira"]
    connection: Literal["local", "skill", "mcp"]
    project: str = Field(min_length=1)
    path: str | None
    skill: str | None
    mcp: str | None
    capabilities: list[str] = Field(min_length=1)


class Pain(StrictModel):
    description: str = Field(min_length=1)
    impact: str = Field(min_length=1)
    frequency: str = Field(min_length=1)


class ProfileFact(StrictModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    statement: str = Field(min_length=1)
    evidence: str = Field(min_length=1)


class DraftProfile(StrictModel):
    schema_version: Literal[1]
    customer_id: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    name: str = Field(min_length=1)
    sdlc: list[SdlcStage] = Field(min_length=1)
    glossary: dict[str, str]
    systems: list[DeclaredSystem]
    issue_tracker: IssueTracker
    roles: list[str] = Field(min_length=1)
    pains: list[Pain]
    success_criteria: list[str] = Field(min_length=1)
    constraints: list[str]
    facts: list[ProfileFact]
    assumptions: list[str]
    unknowns: list[str]


class GlossaryEntry(StrictModel):
    term: str = Field(min_length=1)
    definition: str = Field(min_length=1)


class WireDraftProfile(DraftProfile):
    glossary: list[GlossaryEntry]

    @model_validator(mode="after")
    def require_unique_glossary_terms(self) -> "WireDraftProfile":
        terms = [entry.term for entry in self.glossary]
        if len(terms) != len(set(terms)):
            raise ValueError("glossary terms must be unique")
        return self


class ManualHandoff(StrictModel):
    owner: str = Field(min_length=1)
    instructions: str = Field(min_length=1)
    resume_when: str = Field(min_length=1)


class WorkflowStep(StrictModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    name: str = Field(min_length=1)
    skill: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    needs: list[str]
    inputs: list[str]
    outputs: list[str]
    tools: list[str]
    effect: Literal["read", "local", "external-write", "manual"]
    approval: bool
    approval_timing: Literal["before", "after"] = "before"
    approver: str | None
    completion: str = Field(min_length=1)
    failure: str = Field(min_length=1)
    manual: ManualHandoff | None


class TraceabilityEntry(StrictModel):
    requirement: str = Field(min_length=1)
    steps: list[str]
    checks: list[str]


class DraftWorkflow(StrictModel):
    schema_version: Literal[1]
    id: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    name: str = Field(min_length=1)
    customer_id: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    goal: str = Field(min_length=1)
    trigger: str = Field(min_length=1)
    inputs: list[str] = Field(min_length=1)
    outputs: list[str] = Field(min_length=1)
    customer_rules: list[str]
    steps: list[WorkflowStep] = Field(min_length=1)
    traceability: list[TraceabilityEntry]


class Scenario(StrictModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    given: str = Field(min_length=1)
    expect: Literal[
        "awaiting-answer",
        "awaiting-approval",
        "awaiting-manual",
        "blocked",
        "cancelled",
        "failed",
        "uncertain",
        "completed",
    ]
    forbidden: list[str]


class DraftScenarios(StrictModel):
    schema_version: Literal[1]
    workflow: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    mode: Literal["read-only-agent-simulation"]
    scenarios: list[Scenario] = Field(min_length=1)


class DraftCandidate(StrictModel):
    profile: DraftProfile
    workflow: DraftWorkflow
    scenarios: DraftScenarios


class WireDraftCandidate(StrictModel):
    profile: WireDraftProfile
    workflow: DraftWorkflow
    scenarios: DraftScenarios

    def to_canonical(self) -> DraftCandidate:
        value = self.model_dump()
        value["profile"]["glossary"] = {
            entry.term: entry.definition
            for entry in sorted(self.profile.glossary, key=lambda item: item.term)
        }
        return DraftCandidate.model_validate(value)
