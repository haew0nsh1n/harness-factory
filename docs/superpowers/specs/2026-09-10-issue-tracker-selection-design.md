# Issue Tracker Selection and Connection Guide 설계

날짜: 2026-09-10

상태: 사용자가 Git+Markdown, Jira, GitHub Issues 선택과 스킬 우선·MCP 폴백을 요청하여 설계 확정.

## 1. 목표

Harness Factory 인터뷰에서 고객의 이슈 시스템을 다음 중 하나로 선택하고, 생성된 고객 패키지에 실제 준비 절차와 검증 상태를 포함한다.

1. Git + Markdown
2. GitHub Issues
3. Jira

GitHub Issues와 Jira는 고객 환경에 호환 스킬이 있으면 그 스킬을 우선 사용한다. 없으면 MCP 연결을 안내한다. 둘 다 준비되지 않은 상태를 연결 완료로 표시하지 않는다.

## 2. 접근 방식

**내장 로컬 어댑터 + 외부 스킬 우선 + MCP 폴백**을 사용한다.

- Git+Markdown은 팩토리가 검증한 `hf-issues-markdown` 스킬을 패키지에 포함한다.
- GitHub Issues와 Jira는 기존 고객 스킬을 패키지에 복제하지 않는다. 라이선스·버전·자동 업데이트 정책을 알 수 없기 때문이다. 대신 고객 환경의 Copilot 지원 스킬 위치에서 명시된 후보 스킬 이름을 탐색한다.
- 호환 스킬이 없으면 프로필에 선언한 `mcp:github` 또는 `mcp:jira`를 폴백으로 사용한다.
- 자동 탐색 결과는 준비 상태일 뿐, 스킬 동작이나 MCP 권한의 보증이 아니다. 읽기·쓰기 기능을 별도로 확인한다.

정적 GitHub/Jira 커넥터를 팩토리에 직접 내장하는 방식은 인증과 API 유지보수 범위를 크게 늘리므로 제외한다. MCP 전용 방식은 이미 설치된 고객 스킬을 활용하지 못하므로 선택하지 않는다.

## 3. 고객 프로필 계약

프로필에 필수 `issue_tracker` 객체를 추가한다.

```json
{
  "system_id": "issues",
  "provider": "markdown",
  "connection": "local",
  "project": "product",
  "path": "issues",
  "skill": null,
  "mcp": null,
  "capabilities": ["issue-read", "issue-create", "issue-update"]
}
```

공통 필드:

- `system_id`: `systems` 배열의 이슈 시스템 ID.
- `provider`: `markdown`, `github`, `jira`.
- `connection`: `local`, `skill`, `mcp`.
- `project`: 사람에게 보여줄 프로젝트 식별자. GitHub는 `owner/repository`, Jira는 project key, Markdown은 저장소 내 논리 프로젝트명.
- `path`: Markdown일 때 저장 디렉터리. 기본 `issues`; 다른 provider는 `null`.
- `skill`: 선택된 GitHub/Jira 연결 스킬 이름 또는 `null`.
- `mcp`: 폴백 MCP 도구 토큰(`mcp:github`, `mcp:jira`) 또는 `null`.
- `capabilities`: 필요한 기능. `issue-read`, `issue-create`, `issue-update`, `issue-transition`, `issue-comment` 중 선택한다.

조합 규칙:

- Markdown: `connection=local`, `path` 필수, `skill=null`, `mcp=null`.
- 스킬 선택: `connection=skill`, `skill` 필수, `mcp`는 선택적 대체 안내.
- 명시적 MCP: `connection=mcp`, `mcp` 필수.
- 고객 시스템의 토큰·비밀번호·서버 비밀은 저장하지 않는다.

기존 `systems`에는 실제 도구 바인딩을 유지한다. Markdown은 `tool: git`, GitHub/Jira 스킬 모드는 `tool: skill:<name>`, MCP 모드는 `tool: mcp:<name>`을 사용한다. `system_id`가 참조한 시스템의 tool과 connection이 일치해야 한다. 계약 검증기는 `skill:<name>` 토큰을 허용하도록 확장한다.

## 4. 인터뷰와 선택 흐름

이슈 처리 단계가 관련된 고객에게 한 번에 하나씩 묻는다.

1. 현재 이슈 원본은 Git 저장소 Markdown, GitHub Issues, Jira 중 무엇인가?
2. 프로젝트 또는 저장소 식별자는 무엇인가?
3. 필요한 기능은 읽기, 생성, 수정, 상태 전환, 댓글 중 무엇인가?
4. GitHub/Jira라면 현재 Copilot에서 사용하는 이슈 트래커 스킬이 있는가?
5. 없다면 조직이 승인한 MCP 서버가 있는가? 이름만 기록하고 비밀값은 받지 않는다.

팩토리는 선택 전환 시 기존 워크플로우의 도구 바인딩과 수동 경로를 다시 검토한다. 쓰기 capability에는 고객이 지정한 승인 역할이 필요하다.

## 5. 스킬 탐색과 연결 계획

팩토리 인터뷰는 후보 스킬 이름을 받은 뒤 아래 경로에서 스킬을 탐색한다. 발견한 스킬을 고객이 호환 가능하다고 확인하면 `connection=skill`로 프로필을 확정하고, 없으면 `connection=mcp`로 확정한다. 최종 패키지는 런타임에 연결 방식을 자동 변경하지 않는다.

`tracker-guide --profile FILE [--target DIR]` 명령을 추가한다. 명령은 확정된 연결을 변경하지 않고 결정론적 설치·검증 계획을 반환한다.

Copilot 지원 위치를 다음 순서로 검사한다.

1. 대상 저장소 `.agents/skills/<name>/SKILL.md`
2. 대상 저장소 `.github/skills/<name>/SKILL.md`
3. 대상 저장소 `.claude/skills/<name>/SKILL.md`
4. `~/.copilot/skills/<name>/SKILL.md`
5. `~/.agents/skills/<name>/SKILL.md`

선택된 `skill`은 안전한 스킬 식별자여야 한다. 도구는 후보 파일의 존재, symlink 여부, frontmatter `name` 일치만 확인한다. 스킬이 실제 provider/capability를 지원한다고 추론하지 않는다. 고객 또는 컨설턴트가 호환성을 확인해야 한다.

결과:

- Markdown: `selected=local`, 내장 스킬과 저장 경로, 초기화 안내.
- 스킬 확인: `selected=skill`, 발견 위치와 수동 capability 확인 목록.
- 선택한 스킬 없음: `selected=blocked`, 설정된 MCP가 있으면 재생성 때 MCP 선택을 권장한다.
- MCP 선택: `selected=mcp`, Copilot `/mcp`에서 서버 설정·인증 후 capability를 확인하는 안내.
- 필요한 설정 없음: `selected=blocked`, 프로필 수정 또는 수동 처리.

프로젝트 밖 개인 스킬 탐색은 이름과 경로 존재 여부만 보고하며 파일 내용을 패키지나 보고서에 복사하지 않는다.

## 6. Git + Markdown 내장 스킬

`hf-issues-markdown`은 저장소 내 `<path>/<issue-id>.md`를 관리한다.

필수 frontmatter:

```yaml
---
id: issue-id
title: Short title
status: open
owners: []
labels: []
created: 2026-09-10
updated: 2026-09-10
---
```

본문 섹션:

- Summary
- Acceptance criteria
- Context
- Work log

상태는 `open`, `in-progress`, `blocked`, `review`, `done`, `cancelled`만 허용한다. 파일 이름과 `id`가 일치해야 한다. 생성·수정은 로컬 파일 변경이며, Git commit/push는 별도 승인과 기존 저장소 절차를 따른다.

스킬은 파일 생성·읽기·업데이트 절차를 제공하지만 자체 CLI 파서는 이번 범위에 추가하지 않는다. 워크플로우의 기존 리뷰와 테스트 단계가 파일 변경을 검증한다.

## 7. 생성 패키지와 설치 가이드

생성된 `.harness/customer.json`에 최소화된 `issue_tracker` 설정을 보존한다. `INSTALL.md`는 다음을 포함한다.

- 선택 provider, 프로젝트 및 필요한 capability.
- 선택 우선순위: local 또는 발견한 skill, 그렇지 않으면 MCP.
- 스킬 후보를 찾는 경로와 확인 결과.
- MCP 폴백의 `/mcp` 설정·인증·기능 확인 단계.
- 쓰기 capability에 필요한 승인과 실행 전 확인.
- 연결 준비가 완료되지 않았을 때의 명시적 blocker.

`preflight`와 `delivery-check`는 tracker 항목을 별도로 보고한다. 스킬 발견은 `available`, MCP는 기존처럼 `manual`, Markdown은 저장 경로와 Git 실행 파일을 점검한다. 어떤 경우에도 스킬 존재나 MCP 로그인만으로 쓰기 capability를 검증했다고 표시하지 않는다.

## 8. 오류 처리

- 안전하지 않은 Markdown 경로, 절대 경로, 저장소 밖 경로: 계약 오류. 계약은 경로를
  순수 문자열로 검증하고, 실제 target의 symlink 구성요소는 tracker guide와 preflight가 검사한다.
- GitHub project는 `owner/repository`, Jira project는 project key, Markdown project는
  안전한 논리 이름만 허용한다. URL, 줄바꿈, 사용자 정보가 포함된 값은 거절한다.
- 잘못된 provider/connection 조합: 계약 오류.
- 후보 스킬 파일이 symlink이거나 frontmatter 이름 불일치: 사용할 수 없는 후보로 보고 다음 후보를 검사.
- `connection=skill`인데 선택 스킬 없음: blocked. 설정된 MCP가 있으면 프로필을 MCP 선택으로 다시 생성하도록 안내한다.
- `connection=mcp`인데 MCP가 없음: blocked 및 프로필 수정.
- 쓰기 capability가 있지만 워크플로우 승인 지점이 없음: 계약 오류. 원격 provider는
  승인된 `external-write` 또는 manual, Markdown은 승인된 `local` 또는 manual이어야 한다.
- 외부 이슈 생성·수정 결과가 불명확하면 기존 uncertain 재시도 방지를 적용한다.

## 9. 테스트

- 각 provider와 유효한 connection 조합.
- Markdown 기본/사용자 경로와 traversal 거절.
- 프로젝트·개인 스킬 탐색 우선순위, symlink와 frontmatter 불일치 건너뛰기.
- 명시적 skill 모드에서 후보 없음 blocker.
- auto 모드 skill 발견과 MCP 폴백.
- MCP 없는 auto blocker.
- preflight가 스킬 존재를 권한 검증으로 승격하지 않음.
- GitHub/Jira 쓰기 capability의 승인 누락 거절.
- 생성 패키지에 선택과 연결 가이드가 보존됨.
- `hf-issues-markdown`의 frontmatter와 필수 절차에 대한 정적 검증.
