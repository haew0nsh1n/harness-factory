import json

from .model import InterviewContext


KOREAN_OUTPUT_POLICY = """모델이 생성하는 모든 자연어 콘텐츠는 정중하고 자연스러운 한국어로 작성하세요.
입력, 이전 대화, 고객 답변이 영어이거나 다른 언어여도 새로 생성하는 첫 질문과 모든 후속 질문,
중간 질문, 설명, 요약, 근거 문장, 사실, 가정, 미확인 사항 및 초안의 사람이 읽는 문구에는
이 규칙을 일관되게 적용하세요. 필요한 경우 제품명과 사용자가 직접 말한 인용문은 원문을
유지하세요. ID, enum, capability, 객체 key, 파일 경로, 명령, schema 값과 제공된 canonical
authority 값은 기계 판독 값이므로 번역하거나 변경하지 마세요. 특히 proposed_scope와
workflow.id는 selected_scope에 쓰이는 동일한 기계 식별자를 그대로 유지하고 번역하지 마세요.
이전 대화 기록 자체를 다시 쓰거나 번역하지 말고, 이번 응답에서 새로 생성하는 자연어만
한국어로 작성하세요.

"""


INTERVIEW_INSTRUCTIONS = KOREAN_OUTPUT_POLICY + """You conduct an adaptive SDLC interview.
Ask exactly one concrete next question, beginning with the selected bottleneck.
Cover only relevant lifecycle stages. Separate facts, assumptions, and unknowns.
Use only supplied turn IDs for evidence; your evidence IDs are temporary proposal
references that the server will replace. Propose one workflow scope.
You have no tools and cannot approve, publish, mutate a catalog, or claim verification.
Return only the requested structured response."""

DRAFT_INSTRUCTIONS = KOREAN_OUTPUT_POLICY + """Create strict candidate profile, workflow, and scenario documents.
Use only the supplied authoritative catalog IDs and capabilities. Do not copy or mutate
catalog bodies. Do not include workflow approval: a human and server supply it later.
Do not invent connector verification, evaluation receipts, identities, or timestamps.
The workflow id must equal the selected scope and scenarios.workflow. Every workflow
step skill must exactly match a supplied catalog skill id. Its effect must be one of
that catalog skill's effects. Its tools must include every capability in that skill's
requires list, expressed only as <declared-system-id>.<capability>; every such capability
must also appear on that declared profile system. Do not add any other tool binding.
Use a manual step when the interview does not establish a compatible connector.
The issue_tracker.system_id must name one declared profile system, and its capabilities
must be a subset of that system's capabilities and only issue-read, issue-create,
issue-update, issue-transition, or issue-comment. Markdown uses local+git+safe relative
path; GitHub/Jira use skill or mcp, no path, and matching system tool and connection.
Give every workflow step a unique id;
each needs entry and traceability step must name an actual workflow step, without cycles.
Each step input must come from workflow inputs or an ancestor step output, and every
workflow output must be produced. The scenarios workflow id must match the workflow id.
Before returning, check the full candidate against these referential-integrity rules and
the catalog, system, effect, approval, artifact, tool, and scenario contracts.
Prefer the smallest complete candidate justified by the confirmed evidence: include only
relevant lifecycle entries, workflow steps, traceability, and one minimal scenario for
each behavior needed to express the selected scope. Do not elaborate unsupported process.
Return only the requested structured response."""


def context_input(context: InterviewContext) -> str:
    return json.dumps(context.model_dump(mode="json"), ensure_ascii=False)


def draft_input(context: InterviewContext, catalog: dict[str, object]) -> str:
    return json.dumps(
        {"context": context.model_dump(mode="json"), "catalog": catalog},
        ensure_ascii=False,
    )
