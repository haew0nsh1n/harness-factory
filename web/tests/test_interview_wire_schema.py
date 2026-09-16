import pytest
from openai.lib._parsing._responses import type_to_text_format_param
from pydantic import ValidationError

from web.api.interviews.schemas import (
    DraftCandidate,
    SYSTEM_TOOL_PATTERN,
    TOOL_BINDING_PATTERN,
    WireDraftCandidate,
    WireInterviewReply,
)
from web.tests.test_interview_proposals import candidate_value


def _wire_candidate_value() -> dict[str, object]:
    value = candidate_value()
    value["profile"]["glossary"] = [
        {"term": term, "definition": definition}
        for term, definition in value["profile"]["glossary"].items()
    ]
    for step in value["workflow"]["steps"]:
        step["approval_timing"] = step.get("approval_timing", "before")
    return value


def _non_null_defaults(value: object, path: str = "$") -> list[str]:
    if isinstance(value, dict):
        found = (
            [path]
            if "default" in value and value["default"] is not None
            else []
        )
        return found + [
            item
            for key, child in value.items()
            for item in _non_null_defaults(child, f"{path}.{key}")
        ]
    if isinstance(value, list):
        return [
            item
            for index, child in enumerate(value)
            for item in _non_null_defaults(child, f"{path}[{index}]")
        ]
    return []


def test_response_wire_schemas_have_no_non_null_defaults():
    for wire_type in (WireInterviewReply, WireDraftCandidate):
        formatted = type_to_text_format_param(wire_type)
        assert _non_null_defaults(formatted) == []


def test_wire_draft_requires_timing_while_canonical_draft_keeps_fallback():
    value = _wire_candidate_value()
    value["workflow"]["steps"][0].pop("approval_timing")

    canonical_value = {
        **value,
        "profile": {
            **value["profile"],
            "glossary": {
                entry["term"]: entry["definition"]
                for entry in value["profile"]["glossary"]
            },
        },
    }
    canonical = DraftCandidate.model_validate(canonical_value)
    assert canonical.workflow.steps[0].approval_timing == "before"

    try:
        WireDraftCandidate.model_validate(value)
    except ValidationError as exc:
        assert any(
            error["loc"][-1] == "approval_timing" for error in exc.errors()
        )
    else:
        raise AssertionError("wire draft accepted a missing approval_timing")


def test_wire_draft_converts_to_canonical_without_changing_timing():
    value = _wire_candidate_value()

    canonical = WireDraftCandidate.model_validate(value).to_canonical()

    assert [
        step.approval_timing for step in canonical.workflow.steps
    ] == [step["approval_timing"] for step in value["workflow"]["steps"]]


def test_actual_sdk_wire_tracker_schema_uses_plain_any_of():
    formatted = type_to_text_format_param(WireDraftCandidate)
    tracker = formatted["schema"]["$defs"]["WireDraftProfile"]["properties"][
        "issue_tracker"
    ]

    assert len(tracker["anyOf"]) == 2
    assert "discriminator" not in tracker


def test_wire_markdown_tracker_round_trips_only_with_null_connectors():
    value = _wire_candidate_value()
    value["profile"]["issue_tracker"] = {
        "system_id": "issues",
        "provider": "markdown",
        "connection": "local",
        "project": "issues",
        "path": "issues",
        "skill": None,
        "mcp": None,
        "capabilities": ["issue-read"],
    }

    canonical = WireDraftCandidate.model_validate(value).to_canonical()

    assert canonical.profile.issue_tracker.model_dump() == value["profile"][
        "issue_tracker"
    ]


@pytest.mark.parametrize(
    ("field", "connector"),
    [
        ("skill", "hf-issues-markdown"),
        ("mcp", "mcp:issues"),
    ],
)
def test_wire_markdown_tracker_rejects_remote_connectors(field, connector):
    value = _wire_candidate_value()
    value["profile"]["issue_tracker"] = {
        "system_id": "issues",
        "provider": "markdown",
        "connection": "local",
        "project": "issues",
        "path": "issues",
        "skill": None,
        "mcp": None,
        "capabilities": ["issue-read"],
    }
    value["profile"]["issue_tracker"][field] = connector

    with pytest.raises(ValidationError):
        WireDraftCandidate.model_validate(value)


def test_wire_remote_tracker_round_trips_without_a_path():
    value = _wire_candidate_value()

    canonical = WireDraftCandidate.model_validate(value).to_canonical()

    assert canonical.profile.issue_tracker.model_dump() == value["profile"][
        "issue_tracker"
    ]


@pytest.mark.parametrize(
    ("provider", "project"),
    [
        ("markdown", "issues backlog"),
        ("github", "owner repository"),
        ("jira", "lowercase"),
    ],
)
def test_wire_tracker_rejects_noncanonical_project_tokens(provider, project):
    value = _wire_candidate_value()
    tracker = value["profile"]["issue_tracker"]
    tracker["provider"] = provider
    tracker["project"] = project
    if provider == "markdown":
        tracker.update(
            connection="local",
            path="issues",
            skill=None,
            mcp=None,
        )

    with pytest.raises(ValidationError):
        WireDraftCandidate.model_validate(value)


def test_actual_sdk_declared_system_tool_uses_canonical_token_pattern():
    formatted = type_to_text_format_param(WireDraftCandidate)
    tool = formatted["schema"]["$defs"]["WireDeclaredSystem"]["properties"][
        "tool"
    ]

    assert tool["pattern"] == SYSTEM_TOOL_PATTERN


@pytest.mark.parametrize("tool", ["git", "skill:github-issues", "mcp:github"])
def test_wire_declared_system_accepts_canonical_tool_tokens(tool):
    value = _wire_candidate_value()
    value["profile"]["systems"][0]["tool"] = tool

    parsed = WireDraftCandidate.model_validate(value)

    assert parsed.profile.systems[0].tool == tool


@pytest.mark.parametrize("tool", ["local+git", "git status", "git --version"])
def test_wire_declared_system_rejects_commands_and_shorthand(tool):
    value = _wire_candidate_value()
    value["profile"]["systems"][0]["tool"] = tool

    with pytest.raises(ValidationError):
        WireDraftCandidate.model_validate(value)


@pytest.mark.parametrize(
    ("mutate", "invalid_value"),
    [
        (
            lambda value, invalid: value["profile"]["systems"][0][
                "capabilities"
            ].append(invalid),
            "issue.read",
        ),
        (
            lambda value, invalid: value["workflow"]["inputs"].append(invalid),
            "issue body",
        ),
        (
            lambda value, invalid: value["workflow"]["steps"][0]["tools"].append(
                invalid
            ),
            "github/issue-read",
        ),
        (
            lambda value, invalid: value["workflow"]["traceability"][0][
                "steps"
            ].append(invalid),
            "bad_step",
        ),
    ],
)
def test_wire_machine_fields_reject_noncanonical_identifiers(
    mutate, invalid_value
):
    value = _wire_candidate_value()
    mutate(value, invalid_value)

    with pytest.raises(ValidationError):
        WireDraftCandidate.model_validate(value)


def test_actual_sdk_workflow_tool_uses_canonical_binding_pattern():
    formatted = type_to_text_format_param(WireDraftCandidate)
    tools = formatted["schema"]["$defs"]["WireWorkflowStep"]["properties"][
        "tools"
    ]

    assert tools["items"]["pattern"] == TOOL_BINDING_PATTERN
