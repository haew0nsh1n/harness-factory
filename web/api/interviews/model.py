from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from .schemas import DraftCandidate, InterviewReply, Stage


class ImmutableModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class InterviewTurn(ImmutableModel):
    id: str = Field(min_length=1, max_length=128)
    role: Literal["user", "assistant"]
    text: str = Field(min_length=1)


class ConfirmedEvidence(ImmutableModel):
    id: str = Field(min_length=1, max_length=128)
    statement: str = Field(min_length=1)
    source_turn_ids: tuple[str, ...]


class InterviewContext(ImmutableModel):
    session_id: str = Field(min_length=1, max_length=128)
    revision: int = Field(ge=0)
    turns: tuple[InterviewTurn, ...]
    confirmed_evidence: tuple[ConfirmedEvidence, ...]
    stage: Stage
    selected_scope: str | None


class InterviewModel(Protocol):
    async def next_question(self, context: InterviewContext) -> InterviewReply: ...

    async def propose_design(
        self, context: InterviewContext, catalog: dict[str, object]
    ) -> DraftCandidate: ...

    async def close(self) -> None: ...
