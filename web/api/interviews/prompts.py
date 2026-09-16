import json

from .model import InterviewContext


KOREAN_OUTPUT_POLICY = """모델이 생성하는 모든 자연어 콘텐츠는 정중하고 자연스러운 한국어로 작성하세요.
입력, 이전 대화, 고객 답변이 영어이거나 다른 언어여도 새로 생성하는 첫 질문과 모든 후속 질문,
중간 질문, 설명, 요약, 근거 문장, 사실, 가정, 미확인 사항 및 초안의 사람이 읽는 문구에는
이 규칙을 일관되게 적용하세요. 필요한 경우 제품명과 사용자가 직접 말한 인용문은 원문을
유지하세요. ID, enum, capability, 객체 key, 파일 경로, 명령, schema 값과 제공된 canonical
authority 값은 기계 판독 값이므로 번역하거나 변경하지 마세요. 특히 proposed_scope와
workflow.id는 유효한 selected_scope에 쓰이는 동일한 기계 식별자를 그대로 유지하고
번역하지 마세요. 다만 이전 기록의 잘못된 scope 값은 그대로 반복하거나 조용히 정규화하지
마세요.
이전 대화 기록 자체를 다시 쓰거나 번역하지 말고, 이번 응답에서 새로 생성하는 자연어만
한국어로 작성하세요.

"""


ENGLISH_OUTPUT_POLICY = """Write all natural-language content you generate in polite, natural English.
Even if the input, prior conversation, or customer answers are in Korean or another
language, apply this rule consistently to the new first question and every follow-up
question, intermediate question, explanation, summary, evidence statement, fact,
assumption, unknown, and the human-readable phrasing of drafts. Preserve product names
and direct user quotations in their original form when needed. IDs, enums, capabilities,
object keys, file paths, commands, schema values, and provided canonical authority values
are machine-readable, so do not translate or change them. In particular, keep
proposed_scope and workflow.id as the same machine identifiers used in a valid
selected_scope and do not translate them. Do not repeat or silently normalize an invalid
scope value from prior history.
Do not rewrite or translate the prior conversation history itself; write only the new
natural language you generate in this response in English.

"""


INTERVIEW_INSTRUCTIONS = KOREAN_OUTPUT_POLICY + """You conduct an adaptive SDLC interview.
Ask exactly one concrete next question, beginning with the selected bottleneck.
Ask questions only for context.selected_stages, in canonical order; summary is an
implicit terminal stage and must not be interviewed as a selected lifecycle stage.
Necessary prerequisites from unselected stages may be described only as workflow
inputs or manual handoffs, not expanded into an unselected-stage interview.
proposed_scope must be a canonical lowercase hyphen identifier matching
^[a-z][a-z0-9-]*$ (for example review-bottleneck, never review_bottleneck).
If a malformed legacy scope appears in context, propose a new valid identifier rather
than echoing or silently normalizing that malformed value.
For bounded categorical questions such as tools, bottlenecks, or review patterns,
offer 2-5 concrete Korean options. Use no options for nuanced free-text questions.
Options are suggestions, never established user facts, and custom text must always
remain allowed. Never invent a choice or force the user to select an option.
Cover only relevant lifecycle stages. Separate facts, assumptions, and unknowns.
Use only supplied turn IDs for evidence; your evidence IDs are temporary proposal
references that the server will replace. Propose one workflow scope.
You have no tools and cannot approve, publish, mutate a catalog, or claim verification.
Return only the requested structured response."""

DRAFT_INSTRUCTIONS = KOREAN_OUTPUT_POLICY + """Create strict candidate profile, workflow, and scenario documents.
Use only the supplied authoritative catalog IDs and capabilities. Do not copy or mutate
catalog bodies. Do not include workflow approval: a human and server supply it later.
Do not invent connector verification, evaluation receipts, identities, or timestamps.
The workflow id must equal the selected scope and scenarios.workflow. The selected scope
must already be a valid canonical lowercase hyphen identifier matching
^[a-z][a-z0-9-]*$; do not reinterpret, translate, or normalize it. Every workflow step
skill must exactly match a supplied catalog skill id. Its effect must be one of
that catalog skill's effects. Its tools must include every capability in that skill's
requires list, expressed only as <declared-system-id>.<capability>; every such capability
must also appear on that declared profile system. Do not add any other tool binding.
Use a manual step when the interview does not establish a compatible connector.
The issue_tracker.system_id must name one declared profile system, and its capabilities
must be a subset of that system's capabilities and only issue-read, issue-create,
issue-update, issue-transition, or issue-comment. For Markdown, set
issue_tracker.connection to local, the matching declared system.tool to the exact token
git, issue_tracker.path to a safe relative path, and both issue_tracker.skill and
issue_tracker.mcp to null. The catalog workflow skill hf-issues-markdown is not an
issue_tracker.skill connector. GitHub/Jira use skill or mcp, no path, and matching
system tool and connection.
Preserve a known provider project identifier exactly; never translate or fabricate it.
GitHub project identifiers must use owner/repository, Jira project identifiers must use
an uppercase project key, and Markdown project identifiers must be one safe token. When
the connector or project is not established by confirmed evidence, prefer an explicitly
unverified local Markdown tracker and manual workflow step instead of inventing a live
GitHub or Jira project.
Give every workflow step a unique id;
each needs entry and traceability step must name an actual workflow step, without cycles.
Each step input must come from workflow inputs or an ancestor step output, and every
workflow output must be produced. The scenarios workflow id must match the workflow id.
Before returning, check the full candidate against these referential-integrity rules and
the catalog, system, effect, approval, artifact, tool, and scenario contracts.
Prefer the smallest complete candidate justified by the confirmed evidence: include only
context.selected_stages lifecycle entries (and no other SDLC entries), workflow steps,
traceability, and one minimal scenario for
each behavior needed to express the selected scope. Do not elaborate unsupported process.
Represent prerequisites from unselected stages as described workflow inputs or manual
handoffs rather than full unselected lifecycle entries.
Return only the requested structured response."""


def interview_instructions(language: str = "ko") -> str:
    if language == "en":
        body = INTERVIEW_INSTRUCTIONS[len(KOREAN_OUTPUT_POLICY):].replace(
            "2-5 concrete Korean options", "2-5 concrete English options"
        )
        return ENGLISH_OUTPUT_POLICY + body
    return INTERVIEW_INSTRUCTIONS


def draft_instructions(language: str = "ko") -> str:
    if language == "en":
        return ENGLISH_OUTPUT_POLICY + DRAFT_INSTRUCTIONS[len(KOREAN_OUTPUT_POLICY):]
    return DRAFT_INSTRUCTIONS


def context_input(context: InterviewContext) -> str:
    return json.dumps(context.model_dump(mode="json"), ensure_ascii=False)


def draft_input(context: InterviewContext, catalog: dict[str, object]) -> str:
    return json.dumps(
        {"context": context.model_dump(mode="json"), "catalog": catalog},
        ensure_ascii=False,
    )
