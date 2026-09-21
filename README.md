---
title: Harness Factory
description: Design SDLC workflows on the web and deliver them as Copilot CLI harnesses
---

**English** | [한국어](web/README_ko.md)

Harness Factory is a web platform that identifies customer SDLC bottlenecks through
interviews and turns approved workflows into harnesses for Copilot CLI. Authors design
and review workflows in the studio, publish them to the registry, and install verified
packages with the `hf` CLI.

```text
Interview → Workflow design → Validation and approval → Build → Registry publish → Install
```

## Key features

* SDLC interviews that ask one question at a time
* Workflow design and editing based on interview results
* Review and approval bound to exact digests
* Harness package builds in an isolated worker
* Version review, publishing, search, and deprecation in the registry
* Preview and application of published packages with the `hf` CLI

The default catalog includes skills for clarification, planning, test-driven
implementation, code review, manual handoff, and Git-tracked Markdown issues.
Customer-specific rules are added as generated skills without modifying the defaults.

## Issue tracker selection

The interview establishes one of the following as the source of truth. For GitHub
Issues and Jira, the workflow first looks for a customer-approved compatible skill,
then uses an approved MCP connection as a fallback. The selected connection is pinned
in the profile and never switches automatically at runtime.

| Choice | Preferred connection | Fallback | Default storage |
| --- | --- | --- | --- |
| Git + Markdown | bundled `hf-issues-markdown` | manual | `issues/<issue-id>.md` |
| GitHub Issues | approved compatible skill | `mcp:github` | GitHub repository |
| Jira | approved compatible skill | `mcp:jira` | Jira project |

```bash
python3 -m harness_factory tracker-guide \
  --profile examples/github-issue/profile.json --target .
python3 -m harness_factory preflight --package PACKAGE
python3 -m harness_factory delivery-check --package PACKAGE
```

A skill file or MCP name alone does not prove provider compatibility, authentication,
authorization, or capabilities. Authenticate `/mcp` through the customer's approved
native flow and never store credentials in profiles or packages. Changing the
connection method requires another profile review and package generation.

## Included skills

| Skill | Purpose |
| --- | --- |
| `hf-clarify` | Turn prerequisite-aware clarification into an approved brief. |
| `hf-plan` | Turn an approved brief into a scoped, test-first implementation plan. |
| `hf-tdd` | Implement in small red-green-refactor cycles with observed evidence. |
| `hf-review` | Perform a read-only intent and correctness review with evidence handoff. |
| `hf-manual` | Create a human-only handoff with an owner and explicit resume evidence. |
| `hf-issues-markdown` | Manage one Git-tracked Markdown file per issue. |

Sources, pinned revisions, licenses, and Copilot CLI compatibility evidence are
recorded in [`catalog/catalog.json`](catalog/catalog.json).

## Run the web app locally

Docker and Docker Compose are required.

```bash
docker compose up --build
```

Open <http://localhost:3000>. On first run, the stack prepares a development
organization, membership, and sample workflows.

> [!WARNING]
> The local stack uses unverified development identity headers. The API and portal are
> exposed only on `127.0.0.1`; this does not replace production authentication.

Check service health with:

```bash
docker compose ps
curl --fail http://127.0.0.1:8000/api/health
```

## Web workflow

1. Start an interview in the studio and select the SDLC scope.
2. Confirm customer facts, constraints, approvers, and failure handling.
3. Edit and validate the generated design.
4. Request a build after a reviewer approves the current digest.
5. Review the built version and publish it to the registry.
6. Find and install packages with `hf search`, `hf info`, and `hf install`.

An approval is a recorded assertion, not identity authentication or authorization
enforcement. Production deployments must separately configure Microsoft Entra ID,
organization membership, and permissions in customer systems.

## Documentation

* [CLI workflow](docs/cli-workflow.md): standalone generation, checks, installation,
  and execution records
* [Development guide](docs/development.md): development environment, Azure OpenAI
  interviews, and the delivery CLI
* [Operations guide](docs/operations.md): Compose, authentication, retention, and
  acceptance checks
* [Skill contracts](.agents/skills/harness-factory/references/contracts.md): profile
  and workflow fields
* [Skill composition](.agents/skills/harness-factory/references/composition.md):
  catalog and customer-specific skill assembly
* [Design record](docs/superpowers/specs/2026-09-11-harness-factory-web-platform-design.md):
  web platform design background

## Development checks

```bash
uv sync --frozen --no-config --extra test --extra cli
uv run --frozen --no-config --extra test --extra cli pytest
cd web/portal
npm test
npm run typecheck
npm run build
```

See the [operations guide](docs/operations.md) for detailed tests and PostgreSQL
acceptance procedures.

## Project scope

The current implementation provides web-based authoring and registry services, a
Python delivery CLI, and a standalone core. Azure resources and Container Apps
services can be deployed with `azure.yaml` and the Bicep templates in `infra/`.
Microsoft Entra app registration, customer connector creation, customer permission
assignment, and production-readiness validation are not automated.

Catalog sources, pinned commits, licenses, and compatibility evidence are recorded in
[`catalog/catalog.json`](catalog/catalog.json). Original MIT notices are included in
[`catalog/licenses`](catalog/licenses).
