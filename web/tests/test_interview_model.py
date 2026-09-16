import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
import httpx
from openai import APIStatusError
from openai import AsyncOpenAI
from openai.lib._pydantic import to_strict_json_schema
from openai.lib._parsing._responses import type_to_text_format_param
from pydantic import ValidationError

from web.api.config import Settings
from web.api.interviews.azure import AzureOpenAIInterviewModel
from web.api.interviews.errors import InterviewModelError
from web.api.interviews.model import (
    ConfirmedEvidence,
    InterviewContext,
    InterviewTurn,
)
from web.api.interviews.schemas import (
    DraftCandidate,
    InterviewReply,
    WireDraftCandidate,
    WireInterviewReply,
)
from web.api.interviews.prompts import DRAFT_INSTRUCTIONS, INTERVIEW_INSTRUCTIONS


def context(*, answer: str = "Review rework is the bottleneck.") -> InterviewContext:
    return InterviewContext(
        session_id="session-1",
        revision=2,
        turns=(
            InterviewTurn(id="turn-1", role="assistant", text="What is the bottleneck?"),
            InterviewTurn(id="turn-2", role="user", text=answer),
        ),
        confirmed_evidence=(
            ConfirmedEvidence(
                id="evidence-1",
                statement="Review rework is the selected bottleneck.",
                source_turn_ids=("turn-2",),
            ),
        ),
        stage="discovery",
        selected_scope=None,
    )


def initial_context() -> InterviewContext:
    return InterviewContext(
        session_id="session-1",
        revision=0,
        turns=(),
        confirmed_evidence=(),
        stage="discovery",
        selected_scope=None,
    )


def reply(**overrides) -> WireInterviewReply:
    value = {
        "question": "Which planning handoff causes the most delay?",
        "stage": "planning",
        "evidence": [
            {
                "id": "proposal-1",
                "statement": "Review rework is the bottleneck.",
                "kind": "fact",
                "source_turn_ids": ["turn-2"],
            }
        ],
        "proposed_scope": "issue-to-reviewed-change",
        "ready_for_review": False,
        "allow_custom_answer": True,
    }
    value.update(overrides)
    return WireInterviewReply.model_validate(value)


def settings(**overrides) -> Settings:
    values = {
        "auth_mode": "development",
        "allow_insecure_development_auth": True,
        "azure_openai_endpoint": "https://proj-aimain.cognitiveservices.azure.com/",
        "azure_openai_deployment": "gpt-5.6-sol",
    }
    values.update(overrides)
    return Settings(**values)


def candidate_documents() -> tuple[dict, dict, dict, dict]:
    root = Path(__file__).parents[2]
    profile = json.loads((root / "examples/github-issue/profile.json").read_text())
    workflow = json.loads((root / "examples/github-issue/workflow.json").read_text())
    scenarios = json.loads((root / "examples/github-issue/scenarios.json").read_text())
    catalog = json.loads((root / "catalog/catalog.json").read_text())
    workflow.pop("approved")
    return profile, workflow, scenarios, catalog


def wire_candidate(
    profile: dict, workflow: dict, scenarios: dict
) -> WireDraftCandidate:
    profile = dict(profile)
    workflow = dict(workflow)
    workflow["steps"] = [
        {"approval_timing": "before", **step} for step in workflow["steps"]
    ]
    profile["glossary"] = [
        {"term": term, "definition": definition}
        for term, definition in profile["glossary"].items()
    ]
    return WireDraftCandidate.model_validate(
        {"profile": profile, "workflow": workflow, "scenarios": scenarios}
    )


def build_model(parsed, **kwargs):
    responses = SimpleNamespace(parse=AsyncMock())
    responses.parse.return_value = SimpleNamespace(output_parsed=parsed, output=[])
    client = SimpleNamespace(responses=responses, close=AsyncMock())
    credential = SimpleNamespace(close=AsyncMock())
    credential_factory = Mock(return_value=credential)
    token_provider_factory = Mock(return_value=AsyncMock(return_value="token"))
    client_factory = Mock(return_value=client)
    model = AzureOpenAIInterviewModel(
        settings(**kwargs),
        credential_factory=credential_factory,
        token_provider_factory=token_provider_factory,
        client_factory=client_factory,
        retry_delay_seconds=0,
    )
    return (
        model,
        responses,
        client,
        credential,
        credential_factory,
        token_provider_factory,
        client_factory,
    )


def run(coro):
    return asyncio.run(coro)


def test_adapter_uses_async_default_credential_provider_and_bounded_responses_call():
    model, responses, _, _, credential_factory, token_factory, client_factory = (
        build_model(reply())
    )

    result = run(model.next_question(context()))

    assert result.stage == "planning"
    credential_factory.assert_called_once_with(managed_identity_client_id=None)
    token_factory.assert_called_once()
    assert token_factory.call_args.args[1] == "https://cognitiveservices.azure.com/.default"
    assert client_factory.call_args.kwargs["base_url"] == (
        "https://proj-aimain.cognitiveservices.azure.com/openai/v1/"
    )
    assert callable(client_factory.call_args.kwargs["api_key"])
    assert client_factory.call_args.kwargs["max_retries"] == 0
    captured = responses.parse.call_args.kwargs
    assert captured["model"] == "gpt-5.6-sol"
    assert captured["store"] is False
    assert captured["max_output_tokens"] < 8192
    assert captured["text_format"] is WireInterviewReply
    assert "tools" not in captured
    assert "reasoning" not in captured
    assert "verbosity" not in captured


def test_initial_and_followup_questions_request_korean_without_translating_machine_values():
    model, responses, *_ = build_model(reply())
    responses.parse.side_effect = [
        SimpleNamespace(
            output_parsed=reply(evidence=[], proposed_scope=None),
            output=[],
        ),
        SimpleNamespace(output_parsed=reply(), output=[]),
    ]

    run(model.next_question(initial_context()))
    initial_call = responses.parse.call_args_list[0].kwargs
    run(model.next_question(context(answer="GitHub Issues is our source of truth.")))
    followup_call = responses.parse.call_args_list[1].kwargs

    for captured in (initial_call, followup_call):
        assert captured["instructions"].startswith(
            "모델이 생성하는 모든 자연어 콘텐츠는"
        )
        assert "첫 질문과 모든 후속 질문" in captured["instructions"]
        assert "proposed_scope" in captured["instructions"]
        assert "번역하지 마세요" in captured["instructions"]
    assert "GitHub Issues is our source of truth." in followup_call["input"]


def test_real_async_default_credential_can_be_constructed_without_network():
    responses = SimpleNamespace(parse=AsyncMock())
    responses.parse.return_value = SimpleNamespace(
        output_parsed=reply(),
        output=[],
    )
    client = SimpleNamespace(responses=responses, close=AsyncMock())
    model = AzureOpenAIInterviewModel(
        settings(),
        token_provider_factory=Mock(return_value=AsyncMock(return_value="token")),
        client_factory=Mock(return_value=client),
        retry_delay_seconds=0,
    )

    async def exercise():
        result = await model.next_question(context())
        assert result.stage == "planning"
        await model.close()

    run(exercise())
    client.close.assert_awaited_once_with()


def test_optional_managed_identity_client_id_is_passed_to_default_credential():
    model, _, _, _, credential_factory, _, _ = build_model(
        reply(), azure_managed_identity_client_id="managed-client"
    )
    run(model.next_question(context()))
    credential_factory.assert_called_once_with(
        managed_identity_client_id="managed-client"
    )


def test_client_and_credential_are_reused_and_closed_asynchronously():
    model, _, client, credential, credential_factory, _, client_factory = build_model(
        reply()
    )

    async def exercise():
        await model.next_question(context())
        await model.next_question(context())
        await model.close()
        await model.close()

    run(exercise())
    assert credential_factory.call_count == 1
    assert client_factory.call_count == 1
    client.close.assert_awaited_once_with()
    credential.close.assert_awaited_once_with()


def test_failed_client_initialization_closes_owned_credential():
    credential = SimpleNamespace(close=AsyncMock())
    model = AzureOpenAIInterviewModel(
        settings(),
        credential_factory=Mock(return_value=credential),
        token_provider_factory=Mock(return_value=AsyncMock()),
        client_factory=Mock(side_effect=RuntimeError("client init failed")),
    )

    with pytest.raises(RuntimeError, match="client init failed"):
        run(model.next_question(context()))

    credential.close.assert_awaited_once_with()


@pytest.mark.parametrize(
    ("status_code", "code"),
    [(401, "llm_auth_unavailable"), (403, "llm_auth_unavailable"), (429, "llm_throttled")],
)
def test_safe_status_errors(status_code, code):
    model, responses, *_ = build_model(reply())
    response = Mock(status_code=status_code)
    response.request = Mock()
    error = APIStatusError("private provider body", response=response, body=None)
    responses.parse.side_effect = [error, error]

    with pytest.raises(InterviewModelError) as exc:
        run(model.next_question(context()))

    assert exc.value.code == code
    assert "provider" not in str(exc.value).lower()
    assert responses.parse.await_count == (2 if status_code == 429 else 1)


def test_timeout_has_one_bounded_retry():
    from openai import APITimeoutError

    model, responses, *_ = build_model(reply())
    responses.parse.side_effect = APITimeoutError(request=Mock())

    with pytest.raises(InterviewModelError) as exc:
        run(model.next_question(context()))

    assert exc.value.code == "llm_timeout"
    assert responses.parse.await_count == 2


def test_retry_and_wait_complete_within_total_deadline():
    from openai import APITimeoutError

    model, responses, *_ = build_model(reply())
    model._retry_delay_seconds = 0.001
    responses.parse.side_effect = [
        APITimeoutError(request=Mock()),
        SimpleNamespace(output_parsed=reply(), output=[]),
    ]

    assert run(model.next_question(context())).stage == "planning"
    assert responses.parse.await_count == 2


def test_auth_wait_is_cancelled_by_total_deadline():
    provider_cancelled = asyncio.Event()

    async def scenario():
        model, responses, _, _, _, token_factory, _ = build_model(reply())
        model._total_deadline_seconds = 0.01

        async def wait_for_auth():
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                provider_cancelled.set()
                raise

        provider = AsyncMock(side_effect=wait_for_auth)
        token_factory.return_value = provider

        async def parse(**_):
            await provider()

        responses.parse.side_effect = parse
        with pytest.raises(InterviewModelError) as exc:
            await model.next_question(context())
        assert exc.value.code == "llm_timeout"
        assert provider_cancelled.is_set()
        await model.close()

    run(scenario())


def test_late_response_is_rejected_when_transport_suppresses_cancellation():
    async def scenario():
        model, responses, *_ = build_model(reply())
        model._total_deadline_seconds = 0.01

        async def late_response(**_):
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                return SimpleNamespace(output_parsed=reply(), output=[])

        responses.parse.side_effect = late_response
        with pytest.raises(InterviewModelError) as exc:
            await model.next_question(context())
        assert exc.value.code == "llm_timeout"
        await model.close()

    run(scenario())


def test_external_cancellation_propagates():
    async def scenario():
        model, responses, *_ = build_model(reply())
        started = asyncio.Event()

        async def blocked(**_):
            started.set()
            await asyncio.sleep(10)

        responses.parse.side_effect = blocked
        task = asyncio.create_task(model.next_question(context()))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await model.close()

    run(scenario())


def test_refusal_is_distinct_and_safe():
    model, responses, *_ = build_model(reply())
    responses.parse.return_value = SimpleNamespace(
        output_parsed=None,
        output=[
            SimpleNamespace(
                content=[SimpleNamespace(type="refusal", refusal="sensitive provider text")]
            )
        ],
    )

    with pytest.raises(InterviewModelError) as exc:
        run(model.next_question(context()))

    assert exc.value.code == "llm_refused"
    assert "sensitive provider text" not in str(exc.value)


def test_tool_call_output_is_not_accepted_as_a_reply():
    model, responses, *_ = build_model(reply())
    responses.parse.return_value = SimpleNamespace(
        output_parsed=None,
        output=[SimpleNamespace(type="function_call", content=[])],
    )
    with pytest.raises(InterviewModelError) as exc:
        run(model.next_question(context()))
    assert exc.value.code == "llm_invalid_result"


def test_malformed_output_is_rejected():
    model, responses, *_ = build_model(reply())
    responses.parse.return_value = SimpleNamespace(output_parsed=None, output=[])
    with pytest.raises(InterviewModelError) as exc:
        run(model.next_question(context()))
    assert exc.value.code == "llm_invalid_result"


def test_extra_fields_and_multiple_questions_are_rejected_by_schema():
    with pytest.raises(ValidationError):
        InterviewReply.model_validate({**reply().model_dump(), "approved": True})
    with pytest.raises(ValidationError):
        InterviewReply.model_validate(
            {**reply().model_dump(), "question": "What hurts? Who approves?"}
        )


def test_options_are_strict_unique_bounded_and_custom_answer_is_required():
    valid = reply(
        options=[
            {"id": "approval-wait", "label": "승인 대기"},
            {"id": "review-rework", "label": "검토 재작업"},
        ]
    )
    assert valid.allow_custom_answer is True
    with pytest.raises(ValidationError):
        reply(options=[{"id": "same", "label": "하나"}, {"id": "same", "label": "둘"}])
    with pytest.raises(ValidationError):
        reply(options=[{"id": "UPPER", "label": "잘못된 ID"}])
    with pytest.raises(ValidationError):
        reply(options=[{"id": f"choice-{index}", "label": "선택"} for index in range(7)])
    with pytest.raises(ValidationError):
        InterviewReply.model_validate(
            {**valid.model_dump(), "allow_custom_answer": False}
        )


def test_actual_responses_formatter_emits_no_non_null_defaults_for_wire_reply():
    formatted = type_to_text_format_param(WireInterviewReply)

    def assert_no_non_null_defaults(value):
        if isinstance(value, dict):
            assert value.get("default") in (None,)
            for nested in value.values():
                assert_no_non_null_defaults(nested)
        elif isinstance(value, list):
            for nested in value:
                assert_no_non_null_defaults(nested)

    assert_no_non_null_defaults(formatted)
    allow_custom = formatted["schema"]["properties"]["allow_custom_answer"]
    assert allow_custom["const"] is True
    assert "default" not in allow_custom
    assert "allow_custom_answer" in formatted["schema"]["required"]
    assert InterviewReply.model_validate(
        {
            "question": "질문",
            "stage": "review",
            "evidence": [],
            "ready_for_review": False,
        }
    ).allow_custom_answer is True


def test_prompt_requires_korean_suggestions_and_selected_stage_scope():
    assert "2-5 concrete Korean options" in INTERVIEW_INSTRUCTIONS
    assert "context.selected_stages" in DRAFT_INSTRUCTIONS
    assert "review-bottleneck, never review_bottleneck" in INTERVIEW_INSTRUCTIONS
    assert "malformed legacy scope" in INTERVIEW_INSTRUCTIONS
    assert "do not reinterpret, translate, or normalize it" in DRAFT_INSTRUCTIONS


def test_invented_source_turn_id_is_rejected_after_parsing():
    model, *_ = build_model(
        reply(
            evidence=[
                {
                    "id": "proposal-1",
                    "statement": "Invented.",
                    "kind": "fact",
                    "source_turn_ids": ["turn-404"],
                }
            ]
        )
    )
    with pytest.raises(InterviewModelError) as exc:
        run(model.next_question(context()))
    assert exc.value.code == "llm_invalid_result"


def test_answer_limit_fails_before_client_creation():
    model, _, _, _, credential_factory, _, client_factory = build_model(reply())
    with pytest.raises(InterviewModelError) as exc:
        run(model.next_question(context(answer="x" * 8001)))
    assert exc.value.code == "llm_context_limit"
    credential_factory.assert_not_called()
    client_factory.assert_not_called()


def test_full_catalog_and_near_limit_answers_validate_complete_input_before_client():
    _, _, _, catalog = candidate_documents()
    turns = tuple(
        InterviewTurn(
            id=f"turn-{index}",
            role="user" if index % 2 else "assistant",
            text="x" * 7_900,
        )
        for index in range(8)
    )
    large_context = context().model_copy(update={"turns": turns})
    model, _, _, _, credential_factory, _, client_factory = build_model(reply())

    with pytest.raises(InterviewModelError) as exc:
        run(model.propose_design(large_context, catalog))

    assert exc.value.code == "llm_context_limit"
    credential_factory.assert_not_called()
    client_factory.assert_not_called()


def test_missing_configuration_is_explicit_without_constructing_clients():
    client_factory = Mock()
    model = AzureOpenAIInterviewModel(
        settings(azure_openai_endpoint=None, azure_openai_deployment=None),
        client_factory=client_factory,
    )
    with pytest.raises(InterviewModelError) as exc:
        run(model.next_question(context()))
    assert exc.value.code == "llm_not_configured"
    client_factory.assert_not_called()


def test_candidate_rejects_model_authored_approval_catalog_and_untyped_fields():
    with pytest.raises(ValidationError):
        DraftCandidate.model_validate(
            {
                "profile": {},
                "workflow": {"approved": {"by": "model", "at": "now"}},
                "scenarios": {},
                "catalog": {},
            }
        )


def test_sdk_strict_schema_for_wire_candidate_closes_every_object():
    schema = to_strict_json_schema(WireDraftCandidate)

    def assert_closed(value):
        if isinstance(value, dict):
            if value.get("type") == "object":
                assert value.get("additionalProperties") is False
            for nested in value.values():
                assert_closed(nested)
        elif isinstance(value, list):
            for nested in value:
                assert_closed(nested)

    assert_closed(schema)
    glossary = schema["$defs"]["WireDraftProfile"]["properties"]["glossary"]
    assert glossary["type"] == "array"


def test_draft_prompt_binds_catalog_effects_tools_and_selected_scope():
    assert "workflow id must equal the selected scope" in DRAFT_INSTRUCTIONS
    assert "effect must be one of" in DRAFT_INSTRUCTIONS
    assert "<declared-system-id>.<capability>" in DRAFT_INSTRUCTIONS
    assert "Do not add any other tool binding" in DRAFT_INSTRUCTIONS
    assert "issue_tracker.system_id must name one declared profile system" in (
        DRAFT_INSTRUCTIONS
    )
    assert "Preserve a known provider project identifier exactly" in (
        DRAFT_INSTRUCTIONS
    )
    assert "never translate or fabricate it" in DRAFT_INSTRUCTIONS
    assert "unverified local Markdown tracker" in DRAFT_INSTRUCTIONS
    assert "instead of inventing a live" in DRAFT_INSTRUCTIONS
    assert "only issue-read, issue-create" in DRAFT_INSTRUCTIONS
    assert "each needs entry and traceability step must name an actual" in (
        DRAFT_INSTRUCTIONS
    )
    assert "Each step input must come from workflow inputs" in DRAFT_INSTRUCTIONS
    assert "scenarios workflow id must match" in DRAFT_INSTRUCTIONS


def test_wire_glossary_conversion_is_sorted_and_rejects_duplicates():
    profile, workflow, scenarios, _ = candidate_documents()
    workflow["steps"] = [
        {"approval_timing": "before", **step} for step in workflow["steps"]
    ]
    entries = list(profile["glossary"].items())
    profile["glossary"] = [
        {"term": term, "definition": definition}
        for term, definition in reversed(entries)
    ]
    wire = WireDraftCandidate.model_validate(
        {"profile": profile, "workflow": workflow, "scenarios": scenarios}
    )
    canonical = wire.to_canonical()
    assert list(canonical.profile.glossary) == sorted(canonical.profile.glossary)

    profile["glossary"].append(profile["glossary"][0])
    with pytest.raises(ValidationError):
        WireDraftCandidate.model_validate(
            {"profile": profile, "workflow": workflow, "scenarios": scenarios}
        )


def test_propose_design_converts_wire_shape_to_exact_canonical_shape():
    profile, workflow, scenarios, catalog = candidate_documents()
    candidate = wire_candidate(profile, workflow, scenarios)
    model, responses, *_ = build_model(candidate)

    result = run(model.propose_design(context(), catalog))

    assert result.workflow.id == workflow["id"]
    assert result.profile.glossary == profile["glossary"]
    assert "approved" not in result.workflow.model_dump()
    captured = responses.parse.call_args.kwargs
    assert captured["text_format"] is WireDraftCandidate
    assert captured["instructions"].startswith(
        "모델이 생성하는 모든 자연어 콘텐츠는"
    )
    assert "설명, 요약, 근거 문장" in captured["instructions"]
    assert "ID, enum, capability" in captured["instructions"]
    assert "selected_scope" in captured["instructions"]
    assert captured["max_output_tokens"] == 6144
    assert captured["reasoning"] == {"effort": "low"}
    assert captured["text"] == {"verbosity": "low"}
    assert "verbosity" not in captured
    assert "tools" not in captured


def test_actual_sdk_serializes_draft_verbosity_inside_text_config():
    _, _, _, catalog = candidate_documents()
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            400,
            json={
                "error": {
                    "message": "stop after request capture",
                    "type": "invalid_request_error",
                    "code": "captured",
                }
            },
            request=request,
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = AsyncOpenAI(
        api_key="test-token",
        base_url="https://example.invalid/openai/v1/",
        http_client=http_client,
        max_retries=0,
    )
    model = AzureOpenAIInterviewModel(
        settings(),
        credential_factory=Mock(return_value=SimpleNamespace(close=AsyncMock())),
        token_provider_factory=Mock(return_value=AsyncMock(return_value="token")),
        client_factory=Mock(return_value=client),
        retry_delay_seconds=0,
    )

    async def exercise():
        with pytest.raises(InterviewModelError):
            await model.propose_design(context(), catalog)
        await model.close()

    run(exercise())

    assert "verbosity" not in captured
    text = captured["text"]
    assert text["verbosity"] == "low"
    assert text["format"]["type"] == "json_schema"
    assert text["format"]["strict"] is True
    assert text["format"]["schema"]["title"] == "WireDraftCandidate"


def test_propose_design_rejects_invented_catalog_skill():
    profile, workflow, scenarios, catalog = candidate_documents()
    workflow["steps"][0]["skill"] = "invented-skill"
    model, *_ = build_model(wire_candidate(profile, workflow, scenarios))

    with pytest.raises(InterviewModelError) as exc:
        run(model.propose_design(context(), catalog))

    assert exc.value.code == "llm_invalid_result"
