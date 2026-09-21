---
title: Harness Factory
description: 웹에서 SDLC 워크플로를 설계하고 Copilot CLI 하네스로 배포하는 플랫폼
---

[English](../README.md) | **한국어**

Harness Factory는 고객의 SDLC 병목을 인터뷰로 파악하고, 승인된 워크플로를
Copilot CLI용 하네스로 만드는 웹 플랫폼입니다. 스튜디오에서 워크플로를 설계하고
검토한 뒤 레지스트리에 게시하면, 사용자는 `hf` CLI로 검증된 패키지를 설치할 수
있습니다.

```text
인터뷰 → 워크플로 설계 → 검증과 승인 → 빌드 → 레지스트리 게시 → 설치
```

## 주요 기능

* 질문을 한 번에 하나씩 제시하는 SDLC 인터뷰
* 인터뷰 결과를 바탕으로 한 워크플로 설계와 편집
* 정확한 digest를 기준으로 한 검토와 승인
* 격리된 worker를 통한 하네스 패키지 빌드
* 버전별 검토, 게시, 검색, 폐기를 지원하는 레지스트리
* 게시된 패키지를 미리 보고 적용하는 `hf` CLI

기본 카탈로그에는 요구사항 확인, 계획, 테스트 기반 구현, 코드 리뷰, 수동 인계,
Git + Markdown 이슈를 위한 스킬이 포함됩니다. 고객별 규칙은 기본 스킬을
변경하지 않고 별도 생성 스킬로 추가됩니다.

## 이슈 트래커 선택

인터뷰에서 다음 중 하나를 source of truth로 확정합니다. GitHub Issues와
Jira는 고객이 승인한 호환 skill을 먼저 확인하고, 없으면 승인된 MCP 연결을
선택합니다. 연결은 프로필에 고정되며 실행 중 자동 전환하지 않습니다.

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

skill 파일이나 MCP 이름의 존재는 provider 호환성, 인증, 권한 또는 capability
검증이 아닙니다. `/mcp` 인증은 고객의 승인된 네이티브 방식으로 수행하고
자격 증명을 프로필이나 패키지에 저장하지 않습니다. 연결 방식을 바꾸려면
프로필을 다시 검토하고 패키지를 재생성해야 합니다.

## 제공하는 기본 스킬

| Skill | 역할 |
| --- | --- |
| `hf-clarify` | 선행 조건을 확인해 승인 가능한 요구사항 개요를 작성합니다. |
| `hf-plan` | 승인된 개요를 범위가 명확한 테스트 우선 구현 계획으로 변환합니다. |
| `hf-tdd` | 작은 red-green-refactor 주기로 구현하고 관찰된 결과를 기록합니다. |
| `hf-review` | 의도와 정확성을 읽기 전용으로 검토하고 근거를 인계합니다. |
| `hf-manual` | 담당자와 재개 조건이 명확한 사람 전용 인계를 만듭니다. |
| `hf-issues-markdown` | 이슈마다 Git으로 추적하는 Markdown 파일 하나를 관리합니다. |

각 스킬의 출처, 고정 revision, 라이선스와 Copilot CLI 호환성 근거는
[`catalog/catalog.json`](../catalog/catalog.json)에 기록되어 있습니다.

## 로컬에서 웹 실행

Docker와 Docker Compose가 필요합니다.

```bash
docker compose up --build
```

브라우저에서 <http://localhost:3000>을 엽니다. 첫 실행 시 개발 조직, 멤버십,
예제 워크플로가 자동으로 준비됩니다.

> [!WARNING]
> 로컬 스택은 검증되지 않은 개발 신원 헤더를 사용합니다. API와 포털은
> `127.0.0.1`에만 공개되며 운영 인증을 대신하지 않습니다.

서비스 상태는 다음 명령으로 확인할 수 있습니다.

```bash
docker compose ps
curl --fail http://127.0.0.1:8000/api/health
```

## 웹 사용 흐름

1. 스튜디오에서 새 인터뷰를 시작하고 다룰 SDLC 범위를 선택합니다.
2. 고객의 사실, 제약, 승인자와 실패 시 처리 방법을 확인합니다.
3. 생성된 설계를 편집하고 검증합니다.
4. 검토자가 현재 digest를 승인하면 빌드를 요청합니다.
5. 빌드된 버전을 다시 검토하고 레지스트리에 게시합니다.
6. 사용자는 `hf search`, `hf info`, `hf install`로 패키지를 찾고 설치합니다.

승인은 기록된 주장이지 신원 인증이나 권한 강제 수단이 아닙니다. 실제 운영에서는
Microsoft Entra ID, 조직 멤버십, 고객 시스템 권한을 별도로 구성해야 합니다.

## 문서

* [CLI 워크플로](../docs/cli-workflow.md): standalone 생성, 검사, 설치, 실행 기록
* [개발 가이드](../docs/development.md): 개발 환경, Azure OpenAI 인터뷰, 배포 CLI
* [운영 가이드](../docs/operations.md): Compose, 인증, 데이터 보존, 인수 검증
* [스킬 계약](../.agents/skills/harness-factory/references/contracts.md): 프로필과
  워크플로 필드
* [스킬 조립 규칙](../.agents/skills/harness-factory/references/composition.md):
  카탈로그와 고객별 스킬 조립
* [설계 기록](../docs/superpowers/specs/2026-09-11-harness-factory-web-platform-design.md):
  웹 플랫폼의 설계 배경

## 개발 검증

```bash
uv sync --frozen --no-config --extra test --extra cli
uv run --frozen --no-config --extra test --extra cli pytest
cd web/portal
npm test
npm run typecheck
npm run build
```

세부 테스트와 PostgreSQL 인수 절차는 [운영 가이드](../docs/operations.md)를
참고하세요.

## 프로젝트 범위

현재 구현은 웹 기반 authoring과 registry, Python 배포 CLI, standalone core를
제공합니다. `azure.yaml`과 `infra/`의 Bicep 템플릿으로 Azure 리소스와 Container
Apps 서비스를 배포할 수 있습니다. Entra 앱 등록, 고객 커넥터 생성, 실제 고객
권한 부여와 운영 준비 상태 검증은 자동화하지 않습니다.

카탈로그의 출처, 고정 커밋, 라이선스와 호환성 근거는
[catalog/catalog.json](../catalog/catalog.json)에 기록되어 있습니다. 원본 MIT
고지는 [catalog/licenses](../catalog/licenses)에 포함됩니다.
