import asyncio
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar

from azure.core.exceptions import ClientAuthenticationError
from azure.identity.aio import (
    DefaultAzureCredential,
    get_bearer_token_provider,
)
from azure.identity import CredentialUnavailableError
from openai import (
    APIConnectionError,
    APIResponseValidationError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    ContentFilterFinishReasonError,
    LengthFinishReasonError,
)
from pydantic import BaseModel, ValidationError

from web.api.config import Settings

from .errors import InterviewModelError
from .catalog import validate_catalog_references
from .model import InterviewContext
from .prompts import (
    context_input,
    draft_input,
    draft_instructions,
    interview_instructions,
)
from .schemas import (
    DraftCandidate,
    InterviewReply,
    WireDraftCandidate,
    WireInterviewReply,
)


AZURE_COGNITIVE_SCOPE = "https://cognitiveservices.azure.com/.default"
MAX_ANSWER_CHARACTERS = 8_000
MAX_TURNS = 80
MAX_CONTEXT_CHARACTERS = 80_000
TOTAL_DEADLINE_SECONDS = 60.0
RETRY_DELAY_SECONDS = 0.25
TURN_OUTPUT_TOKENS = 2_048
DRAFT_OUTPUT_TOKENS = 6_144
T = TypeVar("T", bound=BaseModel)
R = TypeVar("R")


class AzureOpenAIInterviewModel:
    def __init__(
        self,
        settings: Settings,
        *,
        credential_factory: Callable[..., Any] = DefaultAzureCredential,
        token_provider_factory: Callable[..., Any] = get_bearer_token_provider,
        client_factory: Callable[..., Any] = AsyncOpenAI,
        total_deadline_seconds: float = TOTAL_DEADLINE_SECONDS,
        retry_delay_seconds: float = RETRY_DELAY_SECONDS,
    ) -> None:
        self._settings = settings
        self._credential_factory = credential_factory
        self._token_provider_factory = token_provider_factory
        self._client_factory = client_factory
        self._total_deadline_seconds = total_deadline_seconds
        self._retry_delay_seconds = retry_delay_seconds
        self._credential: Any | None = None
        self._client: Any | None = None
        self._resource_lock = asyncio.Lock()

    async def next_question(self, context: InterviewContext) -> InterviewReply:
        self._validate_context(context)
        input_text = context_input(context)
        instructions = interview_instructions(context.language)
        self._validate_assembled_input(instructions, input_text)

        async def operation() -> InterviewReply:
            wire_result = await self._parse(
                text_format=WireInterviewReply,
                instructions=instructions,
                input_text=input_text,
                max_output_tokens=TURN_OUTPUT_TOKENS,
            )
            result = InterviewReply.model_validate(wire_result.model_dump())
            turn_ids = {turn.id for turn in context.turns}
            if any(
                source_id not in turn_ids
                for evidence in result.evidence
                for source_id in evidence.source_turn_ids
            ):
                raise InterviewModelError(
                    "llm_invalid_result",
                    "The model returned invalid interview evidence.",
                )
            return result

        return await self._within_deadline(operation())

    async def propose_design(
        self, context: InterviewContext, catalog: dict[str, object]
    ) -> DraftCandidate:
        self._validate_context(context)
        input_text = draft_input(context, catalog)
        instructions = draft_instructions(context.language)
        self._validate_assembled_input(instructions, input_text)

        async def operation() -> DraftCandidate:
            wire_result = await self._parse(
                text_format=WireDraftCandidate,
                instructions=instructions,
                input_text=input_text,
                max_output_tokens=DRAFT_OUTPUT_TOKENS,
                reasoning_effort="low",
                verbosity="low",
            )
            try:
                result = wire_result.to_canonical()
            except ValidationError as exc:
                raise InterviewModelError(
                    "llm_invalid_result",
                    "The model returned an invalid structured result.",
                ) from exc
            validate_catalog_references(result, catalog)
            return result

        return await self._within_deadline(operation())

    async def close(self) -> None:
        async with self._resource_lock:
            client, credential = self._client, self._credential
            self._client = None
            self._credential = None
        try:
            if client is not None:
                await client.close()
        finally:
            if credential is not None:
                await credential.close()

    async def _within_deadline(self, operation: Coroutine[Any, Any, R]) -> R:
        loop = asyncio.get_running_loop()
        started = loop.time()
        try:
            async with asyncio.timeout(self._total_deadline_seconds):
                result = await operation
        except TimeoutError as exc:
            raise InterviewModelError(
                "llm_timeout", "Interview inference timed out."
            ) from exc
        if loop.time() - started >= self._total_deadline_seconds:
            raise InterviewModelError("llm_timeout", "Interview inference timed out.")
        return result

    async def _get_client(self) -> Any:
        endpoint = self._settings.azure_openai_endpoint
        deployment = self._settings.azure_openai_deployment
        if not endpoint or not deployment:
            raise InterviewModelError(
                "llm_not_configured", "Interview inference is not configured."
            )
        if self._client is not None:
            return self._client
        async with self._resource_lock:
            if self._client is not None:
                return self._client
            credential = self._credential_factory(
                managed_identity_client_id=(
                    self._settings.azure_managed_identity_client_id
                )
            )
            try:
                provider = self._token_provider_factory(
                    credential, AZURE_COGNITIVE_SCOPE
                )
                client = self._client_factory(
                    base_url=endpoint.rstrip("/") + "/openai/v1/",
                    api_key=provider,
                    timeout=self._total_deadline_seconds,
                    max_retries=0,
                )
            except BaseException:
                await credential.close()
                raise
            self._credential = credential
            self._client = client
            return client

    async def _parse(
        self,
        *,
        text_format: type[T],
        instructions: str,
        input_text: str,
        max_output_tokens: int,
        reasoning_effort: str | None = None,
        verbosity: str | None = None,
    ) -> T:
        client = await self._get_client()
        for attempt in range(2):
            try:
                request_options: dict[str, object] = {
                    "model": self._settings.azure_openai_deployment,
                    "instructions": instructions,
                    "input": input_text,
                    "text_format": text_format,
                    "max_output_tokens": max_output_tokens,
                    "store": False,
                }
                if reasoning_effort is not None:
                    request_options["reasoning"] = {"effort": reasoning_effort}
                if verbosity is not None:
                    request_options["text"] = {"verbosity": verbosity}
                response = await client.responses.parse(
                    **request_options,
                )
            except (CredentialUnavailableError, ClientAuthenticationError) as exc:
                raise InterviewModelError(
                    "llm_auth_unavailable",
                    "Interview model authentication is unavailable.",
                ) from exc
            except (APITimeoutError, APIConnectionError) as exc:
                if attempt == 0:
                    await asyncio.sleep(self._retry_delay_seconds)
                    continue
                raise InterviewModelError(
                    "llm_timeout", "Interview inference is temporarily unavailable."
                ) from exc
            except APIStatusError as exc:
                if exc.status_code in (401, 403):
                    raise InterviewModelError(
                        "llm_auth_unavailable",
                        "Interview model authentication is unavailable.",
                    ) from exc
                if exc.status_code == 429 or exc.status_code >= 500:
                    if attempt == 0:
                        await asyncio.sleep(self._retry_delay_seconds)
                        continue
                    code = "llm_throttled" if exc.status_code == 429 else "llm_timeout"
                    raise InterviewModelError(
                        code, "Interview inference is temporarily unavailable."
                    ) from exc
                raise InterviewModelError(
                    "llm_invalid_result",
                    "The model request did not produce a valid structured result.",
                ) from exc
            except (
                ValidationError,
                APIResponseValidationError,
                LengthFinishReasonError,
            ) as exc:
                raise InterviewModelError(
                    "llm_invalid_result",
                    "The model returned an invalid structured result.",
                ) from exc
            except ContentFilterFinishReasonError as exc:
                raise InterviewModelError(
                    "llm_refused", "The model declined this interview request."
                ) from exc
            parsed = response.output_parsed
            if isinstance(parsed, text_format):
                return parsed
            if parsed is not None:
                raise InterviewModelError(
                    "llm_invalid_result",
                    "The model returned an invalid structured result.",
                )
            if _has_refusal(response):
                raise InterviewModelError(
                    "llm_refused", "The model declined this interview request."
                )
            raise InterviewModelError(
                "llm_invalid_result",
                "The model returned an invalid structured result.",
            )
        raise AssertionError("unreachable")

    @staticmethod
    def _validate_context(context: InterviewContext) -> None:
        if len(context.turns) > MAX_TURNS:
            raise InterviewModelError(
                "llm_context_limit", "The interview reached its turn limit."
            )
        if any(
            turn.role == "user" and len(turn.text) > MAX_ANSWER_CHARACTERS
            for turn in context.turns
        ):
            raise InterviewModelError(
                "llm_context_limit", "An interview answer exceeds the size limit."
            )

    @staticmethod
    def _validate_assembled_input(instructions: str, input_text: str) -> None:
        if len(instructions) + len(input_text) > MAX_CONTEXT_CHARACTERS:
            raise InterviewModelError(
                "llm_context_limit", "The interview reached its context size limit."
            )

def _has_refusal(response: Any) -> bool:
    for output in getattr(response, "output", ()):
        for content in getattr(output, "content", ()):
            if getattr(content, "type", None) == "refusal":
                return True
    return False
