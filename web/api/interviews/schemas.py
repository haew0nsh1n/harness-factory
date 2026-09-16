from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from harness_factory.contracts import PROJECT_PART, SYSTEM_TOKEN, TOOL
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
LifecycleStage = Literal[
    "discovery",
    "planning",
    "implementation",
    "testing",
    "review",
    "release",
    "operations",
]
WORKFLOW_ID_PATTERN = r"^[a-z][a-z0-9-]*$"
SYSTEM_TOOL_PATTERN = "^" + SYSTEM_TOKEN.pattern.removesuffix(r"\Z") + "$"
TOOL_BINDING_PATTERN = "^" + TOOL.pattern.removesuffix(r"\Z") + "$"
MARKDOWN_PROJECT_PATTERN = f"^{PROJECT_PART}$"
REMOTE_PROJECT_PATTERN = (
    f"^(?:{PROJECT_PART}/{PROJECT_PART}|[A-Z][A-Z0-9_-]*)$"
)
MachineId = Annotated[str, Field(pattern=WORKFLOW_ID_PATTERN)]
SystemTool = Annotated[str, Field(pattern=SYSTEM_TOOL_PATTERN)]
ToolBinding = Annotated[str, Field(pattern=TOOL_BINDING_PATTERN)]
McpConnector = Annotated[str, Field(pattern=r"^mcp:[a-z][a-z0-9-]*$")]
TrackerCapability = Literal[
    "issue-read",
    "issue-create",
    "issue-update",
    "issue-transition",
    "issue-comment",
]


class InterviewOption(StrictModel):
    id: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[a-z0-9](?:[a-z0-9_-]{0,62}[a-z0-9])?$",
    )
    label: str = Field(min_length=1, max_length=200)


class StartInterviewRequest(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    customer_id: str = Field(
        min_length=1, max_length=80, pattern=r"^[a-z0-9](?:[a-z0-9-]{0,78}[a-z0-9])?$"
    )
    consent_version: Literal["2026-09-15"]
    consent_accepted: Literal[True]
    language: Literal["ko", "en"] = "ko"
    request_id: UUID = Field(strict=False)
    selected_stages: list[LifecycleStage] | None = Field(
        default=None, min_length=1, max_length=7
    )

    @field_validator("selected_stages")
    @classmethod
    def require_unique_stages(
        cls, value: list[LifecycleStage] | None
    ) -> list[LifecycleStage] | None:
        if value is not None and len(value) != len(set(value)):
            raise ValueError("selected stages must be unique")
        return value


class ChoiceAnswer(StrictModel):
    question_turn_id: UUID = Field(strict=False)
    option_id: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[a-z0-9](?:[a-z0-9_-]{0,62}[a-z0-9])?$",
    )


class AnswerRequest(StrictModel):
    expected_revision: int = Field(ge=0)
    request_id: UUID = Field(strict=False)
    answer: str | None = Field(default=None, min_length=1, max_length=8000)
    choice_answer: ChoiceAnswer | None = None

    @model_validator(mode="after")
    def require_exactly_one_answer(self) -> "AnswerRequest":
        if (self.answer is None) == (self.choice_answer is None):
            raise ValueError("provide exactly one answer or choice_answer")
        if self.answer is not None and not self.answer.strip():
            raise ValueError("answer must not be blank")
        return self


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
    language: Literal["ko", "en"] = "ko"
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
    options: list[InterviewOption] = Field(default_factory=list, max_length=6)
    allow_custom_answer: bool = True
    choice_question_turn_id: str | None = None
    choice_option_id: str | None = None


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
    lease_expired: bool


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
    selected_stages: list[LifecycleStage]
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
    proposed_scope: str | None = Field(
        default=None,
        max_length=256,
        pattern=WORKFLOW_ID_PATTERN,
    )
    ready_for_review: bool
    options: list[InterviewOption] = Field(default_factory=list, max_length=6)
    allow_custom_answer: Literal[True] = True

    @field_validator("question")
    @classmethod
    def require_one_question(cls, value: str) -> str:
        if value.count("?") > 1:
            raise ValueError("question must contain at most one question")
        return value

    @field_validator("options")
    @classmethod
    def require_unique_option_ids(
        cls, value: list[InterviewOption]
    ) -> list[InterviewOption]:
        ids = [option.id for option in value]
        if len(ids) != len(set(ids)):
            raise ValueError("option IDs must be unique")
        return value


class WireInterviewReply(InterviewReply):
    allow_custom_answer: Literal[True]


class SdlcStage(StrictModel):
    stage: str = Field(min_length=1)
    current: str = Field(min_length=1)
    desired: str = Field(min_length=1)


class DeclaredSystem(StrictModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    kind: str = Field(min_length=1)
    tool: str = Field(min_length=1)
    capabilities: list[str] = Field(min_length=1)


class WireDeclaredSystem(DeclaredSystem):
    tool: SystemTool
    capabilities: list[MachineId] = Field(min_length=1)


class IssueTracker(StrictModel):
    system_id: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    provider: Literal["markdown", "github", "jira"]
    connection: Literal["local", "skill", "mcp"]
    project: str = Field(min_length=1)
    path: str | None
    skill: str | None
    mcp: str | None
    capabilities: list[str] = Field(min_length=1)


class WireMarkdownIssueTracker(StrictModel):
    system_id: MachineId
    provider: Literal["markdown"]
    connection: Literal["local"]
    project: str = Field(pattern=MARKDOWN_PROJECT_PATTERN)
    path: str = Field(min_length=1)
    skill: None
    mcp: None
    capabilities: list[TrackerCapability] = Field(min_length=1)


class WireRemoteIssueTracker(StrictModel):
    system_id: MachineId
    provider: Literal["github", "jira"]
    connection: Literal["skill", "mcp"]
    project: str = Field(pattern=REMOTE_PROJECT_PATTERN)
    path: None
    skill: MachineId | None
    mcp: McpConnector | None
    capabilities: list[TrackerCapability] = Field(min_length=1)


WireIssueTracker = WireMarkdownIssueTracker | WireRemoteIssueTracker


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
    systems: list[WireDeclaredSystem]
    issue_tracker: WireIssueTracker

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


class WireWorkflowStep(WorkflowStep):
    needs: list[MachineId]
    inputs: list[MachineId]
    outputs: list[MachineId]
    tools: list[ToolBinding]
    approval_timing: Literal["before", "after"]


class TraceabilityEntry(StrictModel):
    requirement: str = Field(min_length=1)
    steps: list[str]
    checks: list[str]


class WireTraceabilityEntry(TraceabilityEntry):
    steps: list[MachineId] = Field(min_length=1)
    checks: list[str] = Field(min_length=1)


class DraftWorkflow(StrictModel):
    schema_version: Literal[1]
    id: str = Field(pattern=WORKFLOW_ID_PATTERN)
    name: str = Field(min_length=1)
    customer_id: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    goal: str = Field(min_length=1)
    trigger: str = Field(min_length=1)
    inputs: list[str] = Field(min_length=1)
    outputs: list[str] = Field(min_length=1)
    customer_rules: list[str]
    steps: list[WorkflowStep] = Field(min_length=1)
    traceability: list[TraceabilityEntry]


class WireDraftWorkflow(DraftWorkflow):
    inputs: list[MachineId] = Field(min_length=1)
    outputs: list[MachineId] = Field(min_length=1)
    steps: list[WireWorkflowStep] = Field(min_length=1)
    traceability: list[WireTraceabilityEntry] = Field(min_length=1)


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
    workflow: WireDraftWorkflow
    scenarios: DraftScenarios

    def to_canonical(self) -> DraftCandidate:
        value = self.model_dump()
        value["profile"]["glossary"] = {
            entry.term: entry.definition
            for entry in sorted(self.profile.glossary, key=lambda item: item.term)
        }
        return DraftCandidate.model_validate(value)
