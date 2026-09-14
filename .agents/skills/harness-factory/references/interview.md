# Adaptive SDLC interview

Use the customer's language; these are prompts to choose from, not a mandatory
questionnaire to recite. One question per turn. Build a decision tree and resolve
prerequisites before dependent questions. Distinguish decisions from facts.

## Start with a real incident

Ask: "최근 개발 업무에서 가장 오래 막혔던 사례 하나를 처음부터 끝까지 설명해 주세요."
Then identify the initiating event, people, systems, waits and observable result.
Do not accept a desired tool as the problem definition: ask what would improve.

## Sweep the lifecycle

Cover discovery/planning, issue intake, implementation, testing, review, release
and operational feedback. A stage not used by the customer is a fact, not a gap
you should fill with a new process. For each relevant stage learn:

- What starts it, who owns it, and what artifact exits it?
- What is manual, repetitive or frequently reworked?
- Who must approve and who may execute?
- Which system holds the source of truth?
- What cannot leave the environment?

## Deepen the chosen incident

Trace handoffs and re-entry after failure. Ask for frequency and impact as the
customer observes them; do not invent numeric ROI. Discover whether the pain is
requirements ambiguity, missing context, tool friction, slow feedback or policy.

Identify exact issue tracker and repository use, supported MCP/CLI capabilities,
authentication ownership and customer-specific terminology. Do not collect
tokens. An unknown connector is a manual gap until verified.

## Select the issue tracker connection

Use this order and record exactly one tracker choice:

1. Ask whether Git + Markdown, GitHub Issues, or Jira is the source of truth.
2. Record the repository/project and minimum issue capabilities.
3. For GitHub Issues or Jira, check customer-approved Copilot skill choices first.
4. Persist `connection=skill` only after compatibility is confirmed.
5. Otherwise require an approved MCP name and persist `connection=mcp`.
6. If neither exists, record tracker automation as a manual blocker.
7. Never collect credentials and never infer authentication, authorization, or
   capability support from a skill file or MCP name being present.

Git + Markdown persists `connection=local` and a safe repository-relative path,
normally `issues`. Missing skill support does not trigger runtime fallback:
change the approved profile and regenerate the package.

## Confirm understanding

Summarize current versus desired process, facts versus assumptions, roles, shared
terms, success criteria and uncertainties. Resolve conflicting rules explicitly.
Recommend one workflow using stated evidence. A broad SDLC profile may feed many
future workflows, but this generation produces only one.

Influences: Matt Pocock's prerequisite-aware grilling and shared domain language;
Superpowers' approval-before-implementation; gstack's problem-first role framing.
This adaptation intentionally asks one question, rather than a whole frontier
of questions, to suit live consultant interviews.
