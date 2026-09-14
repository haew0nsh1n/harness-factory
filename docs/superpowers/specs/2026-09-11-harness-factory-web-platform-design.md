# Harness Factory Web Platform 설계

날짜: 2026-09-11

상태: 사용자 승인 완료. 구현 계획 작성 전 명세 검토 대기.

## 1. 목표

기존 GitHub Copilot CLI용 Harness Factory를 기업 내부용 관리형 웹
플랫폼으로 확장한다. 웹은 고객 SDLC 인터뷰, 워크플로우 설계와 승인,
패키지 생성, 조직 내 자산 레지스트리, CLI 설치 배포와 사용량 분석을
제공한다.

플랫폼의 핵심 사용자는 다음과 같다.

- 컨설턴트와 작성자: 고객 인터뷰를 진행하고 하네스를 설계한다.
- 검토자: 워크플로우, 자산 계약, 보안과 검증 결과를 검토한다.
- 레지스트리 관리자: 승인된 자산 버전을 조직 배포 채널에 게시하거나
  폐기한다.
- 개발자: 승인된 스킬, 플러그인과 워크플로우를 검색하고 CLI로 설치한다.
- 조직 관리자: 사용자 역할, 게시·설치 정책과 데이터 보존 기간을 관리한다.

첫 웹 버전은 기업 내부 전용이며, Microsoft Entra ID로 조직과 사용자를
인증하고 GitHub를 저장소 생태계로 사용한다. 설치는 로컬 CLI가 레지스트리
artifact를 pull하여 diff와 digest를 확인한 뒤 사용자가 승인하는 방식이다.

## 2. 제품 경계

### 포함

- 적응형 SDLC 인터뷰 세션과 구조화된 고객 프로필.
- 워크플로우 단계, 입출력, 스킬, 승인, 실패와 수동 인계 편집.
- 정확한 profile/workflow/scenario 계약 검증.
- 승인된 설계에서 불변 패키지 artifact 생성.
- Skill, Plugin, Workflow 자산 등록, 버전 관리, 검증, 검토와 게시.
- 조직 내 자산 검색, 버전·검증 근거·출처·사용량 조회.
- CLI 로그인, 검색, 설치 미리보기, digest 승인, 설치와 명시적 upgrade.
- 설치·제거와 실행 시작·완료·실패 이벤트의 최소 텔레메트리.
- 역할 기반 접근 제어, tenant 격리와 감사 로그.

### 제외

- 웹 서버가 고객 저장소에서 에이전트 워크플로우를 직접 실행하는 기능.
- 중앙 서버가 고객의 코드, 프롬프트, 이슈 본문, 파일 경로 또는 결과물을
  수집하는 기능.
- 외부 제작자가 참여하는 공개 마켓플레이스, 결제와 수익 배분.
- GitHub 또는 Jira credential을 control plane에 저장하고 범용 connector를
  실행하는 기능.
- 게시된 자산의 무승인 자동 업데이트 또는 자동 제거.
- 조직 전체의 운영 자동화와 범용 에이전트 실행 엔진.

기존 Harness Factory의 안전 경계를 유지한다. 패키지 생성 성공, 에이전트
모의 평가, 고객 환경 준비와 실제 업무 성공은 서로 다른 상태로 보고한다.
웹 화면에서도 `available`, `verified`, `approved`, `published`, `installed`,
`ready`를 같은 의미로 취급하지 않는다.

## 3. 선택한 아키텍처

**Modular Monolith + 비동기 Builder Worker + 로컬 CLI**를 사용한다.

웹 포털과 API는 하나의 배포 단위로 시작하지만 도메인별 모듈과 저장소
인터페이스를 분리한다. 패키지 생성과 검증처럼 파일 시스템과 CPU를 사용하는
작업만 격리된 worker에서 실행한다. 데이터베이스가 운영 source of truth이며,
게시된 artifact와 manifest는 object storage에 불변으로 저장한다.

초기부터 microservice로 나누지 않는다. 인터뷰, 승인, 레지스트리, 릴리스와
감사 데이터는 일관된 조직 권한과 트랜잭션을 요구하고, MVP에서 분산 시스템의
운영 비용이 이점보다 크기 때문이다. 모듈 간 호출은 명시적인 application
service와 event contract를 사용하여 추후 독립 서비스로 분리할 수 있게 한다.

Git 저장소를 운영 데이터베이스로 사용하지 않는다. 대신 승인된 manifest와
설계 산출물은 선택적으로 Git에 export하여 사람이 diff와 이력을 검토할 수
있게 한다.

### 3.1 기준 기술 스택

구현 계획의 기준 스택은 다음으로 고정한다.

- Web UI: TypeScript와 React 기반 서버 렌더링 프레임워크.
- API: Python 3.12와 FastAPI. 기존 `harness_factory`를 직접 import한다.
- Database: PostgreSQL과 schema migration 도구.
- Worker: API와 같은 Python package를 사용하는 별도 queue consumer.
- Artifact storage: immutable object storage adapter.
- Queue: at-least-once delivery를 제공하는 managed queue adapter.
- Identity: Microsoft Entra ID OIDC/OAuth2와 서버 측 organization mapping.
- CLI: Python package로 시작하며 기존 installer와 receipt 코드를 재사용한다.
- Observability: 구조화 로그, metric과 trace. customer content는 기록하지 않는다.

UI와 API는 monorepo 안의 독립 package로 두고, domain contract와 generated API
client를 통해 연결한다. 저장소, queue, object storage와 identity는 port/interface
뒤에 두어 로컬 테스트에서 대체할 수 있게 한다. 특정 cloud 서비스 선택은 이
도메인 계약을 바꾸지 않아야 한다.

## 4. 구성요소

### 4.1 Web Portal

단일 조직 컨텍스트에서 다음 영역을 제공한다.

- Dashboard: draft, 검토 대기, 게시된 자산, 설치와 최근 실행 상태.
- Harness Studio: 인터뷰, 프로필, workflow canvas, scenario와 승인.
- Asset Registry: Skill, Plugin, Workflow 검색과 상세 정보.
- Releases: validation, review, approval, publish와 revoke.
- Installations: 설치 ID, 자산 버전, 마지막 확인 시각과 상태.
- Usage Analytics: 설치 보급률, invocation 완료·실패, 버전별 추이.
- Audit Log: 승인, 게시, revoke, 역할과 정책 변경.
- Settings: 역할, 배포 채널, 설치 정책, 데이터 보존 기간.

### 4.2 Identity and Policy Module

Microsoft Entra ID의 tenant와 object ID를 플랫폼 조직 및 사용자에 연결한다.
첫 버전의 역할은 다음과 같다.

- `author`: draft 인터뷰, workflow와 asset version 작성.
- `reviewer`: validation 결과 검토와 approve/reject.
- `registry-admin`: approved version 게시, deprecate, revoke.
- `developer`: 게시된 자산 검색, manifest 조회와 설치 token 발급.
- `org-admin`: 멤버십, 역할, 정책과 retention 관리.

서버 API는 UI 표시 여부와 무관하게 조직 및 역할을 매 요청에서 검증한다.
리소스 ID만으로 다른 tenant의 데이터에 접근할 수 없어야 한다.

### 4.3 Harness Studio Module

인터뷰는 한 번에 한 질문을 표시하고 다음을 별도 항목으로 저장한다.

- 고객이 확인한 fact와 근거.
- 아직 검증하지 않은 assumption.
- 실행 전 해결하거나 blocker로 남길 unknown.
- SDLC 단계, 역할, 시스템, 병목, 성공 기준과 제약.
- Git+Markdown, GitHub Issues 또는 Jira 이슈 트래커 선택.

Workflow editor는 단계 DAG, 입출력 artifact, skill version constraint,
tool capability, effect, 승인 시점, 완료 기준, 실패와 manual handoff를
편집한다. 기존 JSON 계약을 canonical representation으로 유지하며 UI의
편집 모델은 해당 계약으로 직렬화되어야 한다.

승인은 정확한 profile, workflow와 scenario revision digest에 결합한다.
승인 후 의미 있는 변경은 기존 승인을 무효화하고 새 review를 요구한다.

### 4.4 Registry Module

공통 `Asset`은 `skill`, `plugin`, `workflow` 타입 중 하나다. 공통 metadata는
조직, slug, 표시 이름, 설명, owner, visibility, lifecycle과 latest channel을
포함한다.

타입별 manifest는 다음을 요구한다.

| 타입 | 필수 계약 | 기본 설치 단위 |
| --- | --- | --- |
| Skill | `SKILL.md`, 입력·출력, effects, requirements, provenance | `.agents/skills/<name>` |
| Plugin | 포함 skill/resource, hook 여부, runtime compatibility, side effects | 검증된 파일 묶음 |
| Workflow | 단계 DAG, skill/plugin version constraints, approvals, scenarios | workflow entry와 dependency lock |

레지스트리는 호환성을 추론하지 않는다. 각 version은 검증 상태, 런타임,
출처, 라이선스, 알려진 제약과 behavior evidence를 명시한다.

### 4.5 Package and Release Module

기존 `harness_factory` Python 코어를 라이브러리로 호출하여 다음을 수행한다.

1. profile, workflow, catalog와 scenario 계약 검증.
2. 선택한 자산 dependency resolution.
3. 정확한 version과 SHA-256 digest를 dependency lock에 기록.
4. 패키지 생성과 manifest 검사.
5. 선택적 read-only behavior evaluation receipt 확인.
6. immutable artifact와 release metadata 생성.

게시된 artifact는 수정할 수 없다. 수정은 새 semantic version과 validation,
review, approval을 요구한다. 서버 서명은 artifact bytes와 manifest digest를
결합하며, 사람의 승인 자체를 대신하지 않는다.

### 4.6 Builder Worker

빌드 job은 queue를 통해 격리 worker에서 실행한다.

- job마다 새로운 작업 디렉터리를 사용하고 종료 시 삭제한다.
- 기본적으로 외부 network를 차단한다.
- archive traversal, 절대 경로, symlink와 특수 파일을 거절한다.
- CPU, 메모리, 파일 크기와 실행 시간을 제한한다.
- 고객 credential을 job 환경에 주입하지 않는다.
- 결과는 artifact, validation findings와 구조화된 build log로 한정한다.

worker 실패를 성공 형태의 artifact로 대체하지 않는다. 실패한 version은
draft 또는 failed validation 상태에 남고 게시할 수 없다.

### 4.7 CLI

별도 `hf` CLI를 제공하고 OS credential store를 통해 Entra device login
token을 보관한다. 주요 명령은 다음과 같다.

```text
hf login
hf search <query>
hf info <asset>[@version]
hf install <asset>@<version>
hf upgrade <asset>
hf uninstall <asset>
hf run-event <asset>@<version> <started|completed|failed>
```

`install`은 manifest와 artifact 서명을 검증하고 대상 저장소의 파일 diff,
충돌과 digest를 보여준다. 사용자가 현재 digest를 승인한 뒤에만 적용한다.
기존 Harness Factory의 managed payload receipt와 고객 파일 보존 규칙을
재사용한다.

`upgrade`는 새 version을 자동 적용하지 않고 동일한 preview와 승인 절차를
거친다. revoke된 버전은 신규 설치를 차단하지만 기존 설치를 자동 삭제하지
않고 경고와 교체 경로를 제공한다.

## 5. 데이터 모델

핵심 entity는 다음과 같다.

- `Organization`: Entra tenant, policy, retention과 상태.
- `User`: Entra object ID, 조직 내 역할과 상태.
- `InterviewSession`: 고객 식별자, 질문·답변 revision과 상태.
- `HarnessDesign`: profile/workflow/scenario revision, digest와 approval 상태.
- `Asset`: 타입, slug, owner, visibility와 lifecycle.
- `AssetVersion`: semver, manifest, digest, artifact URI와 lifecycle.
- `DependencyLock`: consumer version과 dependency version/digest.
- `ValidationRun`: validator version, findings, evidence와 결과.
- `Approval`: subject type/id, exact digest, actor, decision, timestamp.
- `ReleaseChannel`: `pilot`, `stable`과 조직별 접근 정책.
- `Installation`: pseudonymous device/repository ID, asset version과 상태.
- `UsageEvent`: event type, version, outcome, duration bucket와 error class.
- `AuditEvent`: actor, action, resource, immutable change summary와 timestamp.

모든 tenant-owned table은 `organization_id`를 필수로 가진다. API query는
조직 조건 없는 lookup을 허용하지 않는다. 삭제가 필요한 개인정보와 보존해야
하는 감사 event는 별도 retention 정책을 사용한다.

## 6. 버전 및 게시 수명주기

`AssetVersion` 상태는 다음과 같다.

```text
draft -> validating -> validated -> in-review -> approved -> published
                                                \-> rejected
published -> deprecated -> revoked
```

- validation 실패는 `draft`로 돌아가거나 명시적인 `validation-failed` 결과를
  유지한다.
- reviewer approval은 validation이 성공한 exact digest에만 가능하다.
- registry admin은 approved version만 pilot 또는 stable에 게시할 수 있다.
- published version의 manifest, dependencies와 artifact는 불변이다.
- deprecated는 신규 사용을 경고하지만 정책에 따라 설치할 수 있다.
- revoked는 신규 설치를 차단한다.
- 기존 설치는 감사와 복구를 위해 보존하며 자동 삭제하지 않는다.

Workflow version은 모든 skill/plugin dependency를 exact version과 digest로
잠근다. dependency의 새로운 버전이 게시되어도 기존 workflow는 변하지 않는다.

## 7. 주요 데이터 흐름

### 7.1 하네스 생성

1. author가 고객 및 interview session을 생성한다.
2. 포털이 한 질문씩 응답을 수집하고 profile draft를 갱신한다.
3. author가 workflow와 scenario를 작성한다.
4. 서버가 계약 검증을 실행하고 finding을 표시한다.
5. reviewer가 정확한 design digest를 approve 또는 reject한다.
6. approved design을 builder queue에 제출한다.
7. worker가 package를 생성·검사하고 immutable artifact를 저장한다.
8. 결과 workflow version은 registry review와 publish 대상이 된다.

### 7.2 자산 게시

1. author가 skill/plugin/workflow version을 등록한다.
2. worker가 구조, 참조, provenance, license와 behavior evidence를 검증한다.
3. reviewer가 validation finding과 diff를 검토한다.
4. registry admin이 approved digest를 pilot 또는 stable에 게시한다.
5. 게시 event와 actor를 audit log에 기록한다.

### 7.3 CLI 설치

1. 개발자가 `hf search`로 허용된 channel의 자산을 찾는다.
2. CLI가 signed manifest, lock과 artifact를 내려받는다.
3. CLI가 서명·digest와 target 충돌을 검증한다.
4. 추가·변경 파일과 current digest를 표시한다.
5. 개발자가 digest를 승인하면 원자적으로 설치한다.
6. CLI가 내용 없는 installation event를 전송한다.

### 7.4 실행 사용량

생성된 workflow entry 또는 CLI wrapper가 invocation 시작·완료·실패 event를
best-effort로 기록한다. telemetry 전송 실패는 workflow 결과를 실패로 바꾸지
않는다. 외부 write의 uncertain 상태와 telemetry 성공 여부도 결합하지 않는다.

## 8. 텔레메트리

MVP는 다음 event만 수집한다.

- `installation_created`
- `installation_removed`
- `invocation_started`
- `invocation_completed`
- `invocation_failed`

허용 필드는 조직, asset ID/version, runtime, pseudonymous installation/repository
ID, outcome, duration bucket, error class와 timestamp다. 다음은 금지한다.

- 사용자 prompt와 모델 response.
- 이슈 제목·본문, 코드, diff와 artifact 내용.
- 원본 repository URL, branch와 파일 경로.
- access token, cookie, 인증 header와 환경 변수.
- 자유 형식 exception message.

사용자와 저장소 식별자는 조직별 salt로 pseudonymize하고 주기적으로 회전할 수
있어야 한다. CLI는 bounded local queue와 제한된 재시도를 사용하며 이벤트
유실 수만 로컬 진단에 남긴다.

웹은 설치 수, 활성 version, invocation 완료·실패율과 duration bucket을
표시한다. 이 수치를 개발자 생산성이나 개인 성과 평가로 해석하지 않는다는
조직 정책 문구를 제공한다.

## 9. 보안

- Entra tenant와 organization을 명시적으로 연결한다.
- 모든 API에서 tenant condition과 역할을 서버 측에서 확인한다.
- 승인, 게시, revoke와 정책 변경은 immutable audit event를 남긴다.
- artifact 다운로드 URL은 짧은 수명의 scoped URL을 사용한다.
- signing key는 관리형 key service에 보관하고 application process가 raw key를
  읽지 않게 한다.
- 업로드 archive와 Markdown은 untrusted data로 처리한다.
- path traversal, symlink, 특수 파일, 과도한 크기와 압축 폭탄을 거절한다.
- package와 metadata에서 credential-bearing field와 secret pattern을 검사한다.
- customer connector credential은 저장하지 않는다.
- CLI token은 OS credential store에 저장하고 로그에 출력하지 않는다.
- 데이터 export와 deletion은 조직 및 audit retention 정책을 따른다.

## 10. 오류 처리

- validation 실패: version을 게시하지 않고 field/path 기반 finding을 반환한다.
- worker timeout 또는 crash: job을 failed로 기록하고 성공 artifact를 만들지 않는다.
- 승인 후 digest 변경: publish를 거절하고 validation과 approval을 다시 요구한다.
- artifact 다운로드 중단: 부분 파일을 폐기하고 기존 설치를 보존한다.
- 설치 충돌: preview에서 차단하고 무승인 overwrite를 허용하지 않는다.
- 원자적 설치 실패: 가능한 managed file만 rollback하고 불완전 상태를 명시한다.
- telemetry 실패: 실행 결과와 분리하고 bounded retry 후 event를 폐기한다.
- revoked version 요청: 신규 설치를 차단하고 허용된 대체 version을 안내한다.
- 외부 시스템 권한 미확인: `available` 또는 `manual` 상태로 남기고
  `verified`나 `ready`로 승격하지 않는다.

## 11. 테스트 전략

### 기존 코어 회귀

현재 Python 계약, 패키지, 설치, preflight, evaluation과 record 테스트를
library 및 worker 호출 경로에서 동일하게 실행한다. 웹 구현은 기존 143개
테스트를 대체하지 않는다.

### Domain tests

- 조직과 역할별 허용·거절.
- cross-tenant resource ID 접근 거절.
- design/version 상태 전이.
- exact digest에 결합된 approval.
- published artifact 불변성.
- dependency lock과 revoked dependency 처리.
- telemetry 허용·금지 필드.

### Security tests

- archive traversal, symlink, 특수 파일과 압축 폭탄.
- credential-bearing project와 metadata.
- 악의적인 Markdown과 instruction injection.
- IDOR와 tenant query 누락.
- 서명 또는 digest 변조.
- replay된 approval과 만료된 download token.

### Integration tests

- Entra login adapter의 성공, 만료와 tenant mismatch.
- PostgreSQL transaction과 row-level tenant filter.
- object storage upload/download와 immutable key.
- queue의 idempotent job 처리와 timeout.
- CLI signed download, preview, install, conflict와 rollback.

### End-to-end

1. author가 인터뷰에서 profile과 workflow를 만든다.
2. reviewer가 validation 결과를 보고 digest를 승인한다.
3. worker가 workflow artifact를 생성한다.
4. registry admin이 stable에 게시한다.
5. developer가 CLI로 검색하고 preview digest를 승인해 설치한다.
6. invocation 완료 및 실패 event가 원문 없이 analytics에 반영된다.

## 12. MVP 인수 기준

한 Entra tenant 조직에서 다음을 모두 재현할 수 있어야 한다.

1. 컨설턴트가 인터뷰로 고객 profile과 workflow를 작성한다.
2. 계약 위반은 구체적인 finding으로 표시되고 게시를 차단한다.
3. reviewer approval이 정확한 design/version digest에 결합된다.
4. 승인된 workflow를 불변 artifact로 생성하고 stable channel에 게시한다.
5. 개발자가 CLI로 자산을 검색하고 diff·digest 승인 후 설치한다.
6. 기존 고객 파일과 다른 skill은 무승인으로 변경되지 않는다.
7. 설치 수와 invocation 완료·실패가 analytics에 표시된다.
8. code, prompt, issue text와 파일 경로가 telemetry에 포함되지 않는다.
9. 다른 tenant의 resource ID를 사용한 접근이 거절된다.
10. revoked version은 신규 설치가 차단되고 기존 설치는 자동 삭제되지 않는다.

## 13. 구현 분해

전체 플랫폼은 한 번에 구현하지 않고 다음 세 하위 프로젝트로 나눈다.

1. **Web Authoring Core**
   - Entra 조직 인증, Harness Studio, 기존 Python validator 연동,
     design approval과 builder artifact.
2. **Enterprise Asset Registry**
   - 공통 asset/version 모델, validation/review/publish, object storage,
     release channel과 검색.
3. **CLI Distribution and Usage**
   - login, signed manifest, digest preview/install, installation receipt와
     최소 invocation telemetry.

첫 구현 계획은 Web Authoring Core와 레지스트리의 최소 publish/read API를
포함한다. CLI 설치와 사용량 분석은 해당 API 계약이 안정된 후 별도 구현
단계로 진행한다.

## 14. 구현 인수 기록 (2026-09-14)

### 구현 범위

- `docker-compose.yml`에 `postgres`, `api`, `worker`, `portal` 4개 서비스를 구성했다.
- API/worker는 동일한 `web/api/Dockerfile` 이미지를 사용하고,
  API는 시작 전에 `alembic upgrade head`를 수행한다.
- portal은 `web/portal/Dockerfile` 이미지로 실행하며 development identity는
  서버 측 `/api/control-plane/...` 프록시에서만 주입한다.
- named volume `hf-artifacts`를 API/worker에만 마운트하고, worker는 internal
  backend network만 사용해 로컬 스택 기준 외부 egress 없이 동작한다.
- development 전용 `GET /api/audit`를 `org-admin`으로 제한해 acceptance 점검에
  사용했다.

### 정확한 검증 결과

- `.venv/bin/pytest web/tests -q` 실행 결과: **126 passed, 1 skipped**.
  skip은 `HF_POSTGRES_TEST_URL` 미설정 시의 PostgreSQL 인수 테스트다.
- `python3 -m unittest discover -s tests -v` 실행 결과: **143 tests in 13.620s, OK**.
- `cd web/portal && npm test && npm run typecheck && npm run build` 실행 결과:
  **Vitest 7 files / 24 tests passed**, `tsc --noEmit` 성공, `next build` 성공.
- `docker compose config --quiet` 실행 결과: exit 0.
- `docker compose up --build -d` 실행 결과: 4개 서비스와 named volume
  `postgres-data`, `hf-artifacts` 기동.
- `curl --fail http://127.0.0.1:8000/api/health` 실행 결과:
  `{"ok":true,"service":"harness-factory-web","version":"1.1.0"}`.
- `curl --fail http://127.0.0.1:3000` 실행 결과: **HTTP 200**.
- `docker compose exec api python -m web.acceptance.postgres_flow` 실행 결과:
  실제 PostgreSQL에 대해 전체 lifecycle과 cross-tenant 거부를 수행하고
  `{"ok": true, ...}` 반환.
- `docker compose ps` 실행 결과:
  `postgres healthy`, `api healthy`, `portal healthy`, `worker Up`.
- 이후 `docker compose stop`으로 스택을 중지했고 volume 삭제는 수행하지 않았다.

### 인수 플로우 결과

`web/tests/test_acceptance_flow.py`는 다음 순서를 실제로 통과했다.

1. `examples/github-issue`에서 design 생성
2. design validate
3. reviewer exact design digest 승인
4. build queue 후 worker 1회 실행
5. workflow asset와 `1.0.0` version 생성
6. reviewer exact version digest 승인
7. stable publish
8. developer search 및 manifest 조회
9. 다른 tenant가 design/build/asset/version 식별자로 접근 시 404 확인
10. audit event summary key에 `token`, `password`, `secret`, `cookie`,
    `credential`, `prompt`, `source_code`, `diff`, `content` fragment 부재 확인

### 의도적으로 남긴 후속 범위

- CLI distribution (`hf login/search/install/upgrade`)는 아직 구현하지 않았다.
- 설치·실행 usage telemetry와 analytics 집계도 아직 구현하지 않았다.
- 따라서 본 인수는 Web Authoring Core + Registry publish/read 흐름과 로컬
  운영 형태 검증까지를 완료 범위로 기록한다.
