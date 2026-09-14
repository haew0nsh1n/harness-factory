# Harness Factory

고객 인터뷰에서 **Copilot CLI용 아우터 하네스**를 만드는 스킬 기반 생성기입니다.
컨설턴트가 SDLC 전체와 병목을 파악하고, 우선 워크플로우 하나를 선택하면
검토된 기본 스킬과 고객별 규칙을 조립합니다.

```text
고객 인터뷰 → 고객 프로필 → 워크플로우 명세 승인
          → 스킬 조립 → 구조 검사 + 에이전트 모의 평가
          → 설치 변경 승인 → 고객 환경 사전 점검 → 고객이 실행
```

별도 서버나 새 코딩 에이전트는 없습니다. 프로젝트 스킬은
**`.agents/skills/`**를 사용합니다. 기존 MCP 서버·CLI를 활용하며,
없는 연동은 사람의 작업으로 명시합니다.

## 시작하기

필요한 도구는 **Python 3.12 이상**과 **GitHub Copilot CLI**입니다.
Python 외부 패키지는 필요하지 않습니다. `gh`는 GitHub 연동에만 필요하며,
패키지 생성과 오프라인 검사에는 인증이나 네트워크가 필요하지 않습니다.

이 저장소 루트에서 Copilot CLI를 시작합니다.

```bash
copilot
```

다음처럼 요청하세요.

> harness-factory 스킬을 사용해 고객 인터뷰를 시작해 줘.
> 고객은 Jira와 GitHub를 사용하고, 리뷰 단계의 반복 수정이 문제야.

팩토리 진입점은
[`.agents/skills/harness-factory/SKILL.md`](.agents/skills/harness-factory/SKILL.md)입니다.
스킬 파일만 복사하지 말고 `harness_factory/`, `catalog/`, `examples/`를 포함한
전체 체크아웃에서 사용하세요. 고객에게는 생성된 패키지를 전달합니다.

인터뷰는 한 번에 한 질문을 합니다. 비밀번호·토큰·인증 쿠키는 받지 않습니다.
작업용 자료는 Git에서 제외된 `.harness-factory/`에 보관하고,
고객별 작업 디렉터리를 분리합니다.

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

| 역할 | 스킬 | 참고한 원본 |
| --- | --- | --- |
| 요구사항·용어 확인 | `hf-clarify` | Matt Pocock `grilling` |
| 승인된 요구의 실행 계획 | `hf-plan` | Superpowers `writing-plans` |
| 테스트 기반 구현 | `hf-tdd` | Superpowers `test-driven-development` |
| 의도·정확성 리뷰 | `hf-review` | gstack `review` |
| 명시적 수동 인계 | `hf-manual` | Matt Pocock `wizard` |
| Git 추적 Markdown 이슈 | `hf-issues-markdown` | Matt Pocock `wizard` |

단순 이름 참조가 아니라 원본을 읽고 축소·적응한 스킬입니다.
[카탈로그](catalog/catalog.json)에 원본 경로, 고정 커밋, 라이선스와
호환성 근거를 기록했습니다. 원본 MIT 고지는 [catalog/licenses](catalog/licenses)에
있으며 전달 패키지에도 포함됩니다.

원본의 자동 시작 훅, 자동 업데이트, 브라우저·텔레메트리 의존성은 가져오지
않습니다. 동일 역할의 프레임워크 여러 개를 중복 활성화하지 않습니다.
고객 규칙은 기본 스킬을 덮어쓰지 않고 별도 생성 스킬에 둡니다.

`verified`는 [읽기 전용 Copilot 모의 평가](docs/evaluations/2026-09-10-copilot-skills.md)를
통과한 범위의 의미입니다. 운영 인증이나 임의의 고객 워크플로우까지 보장하지
않습니다. 스킬을 변경하면 해당 바이트에 대한 평가 근거도 갱신해야 합니다.
생성된 예제 패키지의 실행·상태 전이 근거는
[고객 하네스 인수 기록](docs/evaluations/2026-09-10-generated-harness.md)에 있습니다.

## 가상 고객으로 생성해 보기

예제는 실제 고객 데이터가 아닙니다. 이슈 명확화 → 계획 → 구현 → 리뷰 →
유지보수 담당자의 수동 PR 발행이라는 워크플로우입니다.
예제의 `approved`는 데모 데이터이며 실제 고객의 승인을 대신하지 않습니다.

```bash
python3 -m harness_factory validate \
  --profile examples/github-issue/profile.json \
  --workflow examples/github-issue/workflow.json \
  --catalog catalog/catalog.json

DEMO=".harness-factory/demo-$(date +%Y%m%d-%H%M%S)-$$"
mkdir "$DEMO/customer"
python3 -m harness_factory tracker-guide \
  --profile examples/github-issue/profile.json \
  --target "$DEMO/customer"

python3 -m harness_factory generate \
  --profile examples/github-issue/profile.json \
  --workflow examples/github-issue/workflow.json \
  --scenarios examples/github-issue/scenarios.json \
  --catalog catalog/catalog.json \
  --output "$DEMO/package"

python3 -m harness_factory check --package "$DEMO/package"
```

생성 전에 고객과 시나리오의 예상 상태와 금지 행동을 검토합니다. 생성된 실제
워크플로우와 스킬을 쓰기 도구·고객 인증·네트워크 없이 읽기 전용 에이전트로
평가하고, 관찰한 응답을 패키지 밖의 결과 파일에 기록합니다.
[예제 결과](examples/github-issue/results.json)는 실제 실행 완료 주장이 아닌
합성 관찰 예시이며, 두 `would_*` 값은 `false`, `observed_forbidden`은 비어 있습니다.
상태를 수동으로 기대값에 맞추거나 금지 행동을 지우는 것은 평가가 아닙니다.

예제 결과의 `<generated-manifest-sha256>`를 방금 생성한 정확한
`.harness/manifest.json` 바이트의 SHA-256으로 바꿉니다. 다음은 원본 예제를
고객별 작업 디렉터리에 복사하고 해시만 치환하는 예입니다.

```bash
cp examples/github-issue/results.json "$DEMO/results.json"
python3 - "$DEMO/package/.harness/manifest.json" "$DEMO/results.json" <<'PY'
import hashlib
import json
import pathlib
import sys

manifest = pathlib.Path(sys.argv[1])
results = pathlib.Path(sys.argv[2])
data = json.loads(results.read_text())
data["package_manifest_sha256"] = hashlib.sha256(manifest.read_bytes()).hexdigest()
results.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
PY
```

원시 결과를 응답별로 검토한 후에만 봉인합니다. `evaluate`는 모델·셸·네트워크·
MCP·고객 도구를 실행하지 않고 계약과 정확한 패키지 바인딩만 검증합니다.
체크인된 플레이스홀더는 그대로 사용하면 거절됩니다.

```bash
python3 -m harness_factory evaluate \
  --package "$DEMO/package" --results "$DEMO/results.json"
python3 -m harness_factory delivery-check --package "$DEMO/package"
python3 -m harness_factory install \
  --package "$DEMO/package" --target "$DEMO/customer"
```

마지막 명령은 **미리보기만** 수행합니다. 추가·변경 파일을 확인한 뒤,
승인한 미리보기의 `digest` 값을 직접 넣어 적용합니다.

```bash
python3 -m harness_factory install \
  --package "$DEMO/package" --target "$DEMO/customer" \
  --approve "<승인한 미리보기의 digest 값>"
```

승인 이후 원본이나 하네스 적용 대상 파일이 달라지면 적용이 거절됩니다. 다시 미리보고
변경을 검토해야 합니다. digest는 변경 내용을 묶는 값이지 사람의 승인을
증명하는 서명이 아닙니다. 생성기는 기존 출력 디렉터리를 덮어쓰지 않습니다.

배포 패키지의 검사는 등록되지 않은 파일도 거절합니다. 설치 후에는
하네스가 소유한 파일과 디렉터리만 보호하므로, 고객 코드·Git 메타데이터·
다른 스킬을 정상적으로 변경할 수 있습니다. 설치된 저장소를 배포 원본으로
재사용하지 말고, 필요하면 승인된 프로필과 명세에서 새 패키지를 생성하세요.

전달 패키지에는 `.agents/skills/`의 선택된 기본 스킬, 고객 규칙과 워크플로우
진입 스킬, `.harness/`의 명세·실행 컨텍스트, 출처·라이선스와 로컬 도구가
포함됩니다. 생성 후 패키지 내 안내에서 실제 진입 스킬 이름을 확인하세요.
고객 저장소에 설치하면 팩토리 체크아웃 없이 그 저장소에서 실행할 수 있습니다.

## 검사 결과를 구분하기

**1. 구조·무결성 검사:** 형식, 의존성, 참조, 승인·실패 경로, 출처 및 패키지
해시를 검사합니다. 구조 검사가 통과했다고 에이전트 동작이 검증된 것은 아닙니다.

**2. 에이전트 모의 평가:** 실제 생성된 스킬을 읽기 전용 평가 에이전트에
제공하고, [예제 시나리오](examples/github-issue/scenarios.json)처럼 가상의 입력과
도구 결과를 전달합니다. 정상 인계, 승인 거절, 연동 누락, 테스트 실패,
중단 후 재개, 불명확한 외부 쓰기 결과와 지시문 삽입에 대한 실제 응답을
기록합니다. 평가 에이전트에는 실제 쓰기 도구와 고객 인증을 제공하지 않습니다.
동작 평가를 수행할 수 없다면 미검증으로 남기며 전달 준비 완료로 표시하지 않습니다.
평가 영수증의 `evaluated_distribution_sha256`는 영수증을 추가하기 전의 정규화된
배포 매니페스트 기준선입니다. 원시 결과는 패키지에 복사하지 않고 그 바이트 해시와
워크플로우·시나리오·선택 스킬 해시만 봉인합니다. 영수증은 신원, 권한, 보안 서명,
운영 인증 또는 실제 업무 완료 증거가 아닙니다.

**3. 고객 환경 사전 점검:** 실제 고객 환경에서 실행합니다.

```bash
python3 -m harness_factory delivery-check --package "$DEMO/package"
```

`delivery-check`는 무결성, 현재 평가 영수증, 기존 사전 점검을 분리해 반환합니다.
`ok: true`는 명령이 실행되었다는 뜻이고 오직 `ready: true`만 구현된 모든 전달
조건의 통과를 뜻합니다. 평가가 없으면 오류가 아니라 `ok: true`, `ready: false`,
`customer_evaluation.status: missing`입니다. 반대로 관리 파일 손상 같은 구조
무결성 오류는 `PackageError`와 0이 아닌 종료 코드로 남아 성공 요약에 숨지 않습니다.

기본 점검은 실행 파일 가용성만 확인하고 인증용 네트워크 호출을 하지 않습니다.
읽기 전용 인증 점검에 명시적으로 동의한 경우에만 다음을 사용합니다.

```bash
python3 -m harness_factory delivery-check \
  --package "$DEMO/package" --allow-read-probes
```

자동 프로브는 알려진 GitHub 읽기 명령으로 제한됩니다. 임의의 프로필 명령을
셸로 실행하지 않습니다. MCP와 미지원 도구는 수동 확인이 필요합니다.
일반 인증 성공은 특정 저장소 접근이나 쓰기 권한의 증거가 아니며,
확인하지 못한 기능은 미확인으로 남깁니다. 실패·미확인이 포함된 사전 점검은
실행 준비 완료를 뜻하지 않습니다.
현재 사전 점검의 `ready: false`는 보통 환경 `unverified`로 유지됩니다.
실행 파일 누락이나 필수 수동 확인은 `blocked`입니다. 전체 사전 점검 결과는
`environment.assessment`에 보존되며 가용성을 기능 통과로 승격하지 않습니다.

## 실행 기록과 재개

설치된 워크플로우 진입 스킬이 현재 명세, 고객 규칙, 산출물과 승인 상태를
확인하며 진행합니다. `record` 도구는 이를 위한 로컬 기록을 지원합니다.

```bash
python3 -m harness_factory record --help
```

예를 들어 생성된 예제에서 첫 단계의 승인과 진행을 기록하는 명령은 다음과
같습니다. 실제 승인 전에 `approved`를 입력하지 마세요. `--by`는 명세의
승인 역할과 일치해야 하지만, 입력자를 인증하는 기능은 아닙니다.

```bash
python3 -m harness_factory record --package . --run issue-demo \
  --step clarify --status running
```

이 예제의 `clarify`와 `plan`은 **산출물 승인** 단계입니다. 먼저 실제 초안을
작성한 다음, 초안의 위치를 근거로 승인 대기를 기록합니다.

```bash
python3 -m harness_factory record --package . --run issue-demo \
  --step clarify --status awaiting-approval --evidence "작성한 brief 초안의 위치"
python3 -m harness_factory record --package . --run issue-demo \
  --step clarify --status awaiting-approval \
  --decision approved --by product-owner --evidence "실제 승인 기록의 참조"
python3 -m harness_factory record --package . --run issue-demo \
  --step clarify --status completed --evidence "확인한 brief 산출물의 위치와 검증 근거"
```

`approval_timing: after`는 초안 작성 후 승인을 요구하며, 승인 전에는 다음
단계로 진행하지 못합니다. `before`는 행동 전 권한 부여이며 생략 시 기본값입니다.
외부 쓰기와 수동 단계에는 `before`만 허용합니다. 두 종류의 승인을 혼동하거나
초안이 나오기 전에 산출물을 승인하지 마세요.

거절은 `--decision denied`로 기록합니다. 수동 단계는 `running` 대신
`awaiting-manual`을 사용하고, 담당자가 결과를 제공한 뒤에만 완료합니다.
`uncertain`은 원래 실행에서 근거와 함께 결과를 확인해야 해소되며,
새 실행 ID로 바꿔 같은 불명확한 작업을 재시도할 수 없습니다.

기록은 `.harness/runs/`에 남습니다. 단순히 이전 상태가 완료라는 이유만으로
계속하지 않고, 실제 산출물이 현재 작업과 일치하는지 확인해야 합니다.
승인 대기와 수동 인계를 완료와 구분합니다. 외부 쓰기 결과가 불명확하면
`uncertain`으로 남기고 원래 작업 결과를 확인하기 전에는 재실행하지 않습니다.

이 도구는 작업을 실행하는 서버나 권한 강제 엔진이 아닙니다.
기록된 승인 역시 사람이 제공한 주장입니다. Copilot 도구 허용 설정과
고객 시스템 권한을 별도로 제한해야 하며, 전체 권한 허용은 요구하지 않습니다.

## 고객별로 바꾸기

전체 필드 계약은
[contracts.md](.agents/skills/harness-factory/references/contracts.md)에 있습니다.
인터뷰 후 프로필과 워크플로우를 작성하고 `validate`를 실행하세요.

- 승인된 워크플로우 하나에 필요한 단계만 선택합니다.
- 단계의 입력은 워크플로우 입력 또는 선행 단계의 산출물이어야 합니다.
- 도구 바인딩은 선언한 시스템의 `<id>.<capability>`만 사용합니다.
- 없는 연동은 담당자·절차·재개 조건이 있는 `manual` 단계로 만듭니다.
- 새로운 스킬은 출처 고정, 계약·라이선스 검토와 모의 평가 이후에 등록합니다.
- 고객 시스템에 접속하기 전에는 승인과 환경 준비를 별도로 확인합니다.

## 개발 및 설계

```bash
python3 -m unittest discover -s tests -v
python3 -m harness_factory --help
```

## 웹 Authoring Registry 로컬 스택

로컬 프로덕션형 검증은 `docker-compose.yml` 하나로 수행합니다.

```bash
docker compose up --build
open http://localhost:3000
```

If your enterprise build environment needs a private package feed, provide it
as an optional build override:

```bash
PIP_INDEX_URL=https://packagefeedproxy.microsoft.io/pypi/simple docker compose up --build
```

- `postgres`: PostgreSQL 16, named volume `postgres-data`.
  `backend` internal network에만 연결되며 호스트로 포트를 노출하지 않습니다.
- `api`: `web/api/Dockerfile` 이미지, 시작 전에 `alembic upgrade head`와
  `python -m web.api.organizations.bootstrap`을 실행한 뒤 Uvicorn을 컨테이너
  8000 포트에 기동하고, 호스트에는 `127.0.0.1:8000`으로만 publish합니다.
- `worker`: API와 같은 Python 이미지를 사용하고 동일한 bootstrap을 실행한 뒤
  `python -m web.api.builds.worker`를 실행합니다. `restart: unless-stopped`로
  DB 재시작이나 연결 단절 이후에도 복구합니다. worker 프로세스는 엔진과
  세션 팩토리를 하나만 만들어 재사용하고, 연결·운영 오류만 지수 backoff로
  제한 재시도합니다. 프로그래밍 오류는 재시도하지 않고 그대로 실패합니다.
- `portal`: `web/portal/Dockerfile` 이미지로 Next.js 포털을 컨테이너 3000 포트에
  띄우고, 호스트에는 `127.0.0.1:3000`으로만 publish합니다.
- API와 worker는 named artifact volume `hf-artifacts`만 `/artifacts`에 마운트합니다.
  worker에는 Docker socket이나 호스트 저장소를 마운트하지 않습니다.
- worker는 Compose의 `backend` internal network에만 연결되어 로컬 스택 기준
  외부 egress 없이 PostgreSQL/API와만 통신합니다.

### 개발 tenant bootstrap

Compose의 PostgreSQL은 비어 있는 상태로 시작하므로 모든 authoring write가
참조하는 개발 조직과 subject membership을 먼저 만들어야 합니다.

```bash
docker compose exec api python -m web.api.organizations.bootstrap
```

- 멱등(idempotent)합니다. 이미 있으면 다시 만들지 않고 역할만 설정값에 맞춥니다.
- `HF_DEVELOPMENT_ORGANIZATION_ID`(기본 `local-dev`),
  `HF_DEVELOPMENT_SUBJECT_ID`(기본 `portal-dev`), `HF_DEVELOPMENT_ROLES`를 씁니다.
  포털 프록시의 `HF_DEV_ORGANIZATION`/`HF_DEV_SUBJECT`/`HF_DEV_ROLES`와 같은 값입니다.
- `HF_AUTH_MODE=development`와 `HF_ALLOW_INSECURE_DEVELOPMENT_AUTH=true`가
  아니면 실행을 거부합니다.
- 존재하지 않는 tenant나 resource를 참조하는 요청은 FK 위반 500이 아니라
  `409 {"ok":false,"error":"referenced tenant or resource does not exist","code":"missing_reference"}`로 응답합니다.

### 개발 인증과 프로덕션 경계

- 개발 인증은 명시적 opt-in입니다. `HF_AUTH_MODE=development`만으로는 기동하지
  않고 `HF_ALLOW_INSECURE_DEVELOPMENT_AUTH=true`가 있어야 API가 시작하며
  개발 헤더를 받아들입니다. 이 헤더는 검증되지 않은 신원 주장이므로 개발 API와
  포털 포트는 루프백(`127.0.0.1`)에만 바인딩합니다. 테스트도 이 옵트인을
  명시적으로 설정합니다.
- `HF_AUTH_MODE=entra` 경로는 이 플래그의 영향을 받지 않습니다. Entra 모드는
  프로세스당 하나의 `EntraTokenValidator`/`PyJWKClient`를 `app.state`에 캐시해
  요청마다 새로 만들지 않습니다.
- 포털 개발 모드는 `NEXT_PUBLIC_HF_AUTH_MODE=development`를 사용합니다.
- 개발 identity는 브라우저가 아니라 포털 서버 프록시가
  `HF_DEV_ORGANIZATION`, `HF_DEV_SUBJECT`, `HF_DEV_ROLES`를 읽어
  `/api/control-plane/...` 요청에만 헤더를 추가합니다.
- 프로덕션 경계는 Entra adapter입니다. 포털은 NextAuth Entra provider를 통해
  bearer token만 API로 전달하고, API는 `HF_AUTH_MODE=entra`와 tenant/member
  매핑으로 조직과 역할을 판정합니다.

### 현재 구현 경계

- design review, build queue, asset version review/publish/revoke는 모두 exact
  digest를 요구하며 stale digest는 거절됩니다. `expected_digest`는 소문자 64자
  SHA-256만 허용하고, 잘못된 값은 `{"ok":false,"error":...,"code":"invalid_request"}`
  구조의 422로 응답합니다.
- asset/channel당 published 버전은 하나입니다. 새 버전을 publish하면 같은
  트랜잭션에서 이전 published 버전이 `deprecated`로 내려가고 이력은 유지됩니다.
- artifact는 API/worker가 공유하는 `/artifacts` 아래 immutable key로 저장합니다.
- CLI 배포(`hf login/search/install/upgrade`)와 설치·실행 usage telemetry는
  후속 구현 범위이며 이번 로컬 스택 인수에 포함되지 않습니다.

### PostgreSQL 인수 실행

전체 lifecycle(create→validate→approve→build→version→approve→publish→search→
manifest)과 cross-tenant 거부를 실제 PostgreSQL에 대해 실행합니다.

```bash
docker compose up --build -d
docker compose exec api python -m web.acceptance.postgres_flow
```

Compose의 PostgreSQL은 internal network에만 있어 호스트에서 직접 접속할 수
없습니다. 같은 흐름을 호스트 pytest로 돌리려면 별도 PostgreSQL을 띄우고
`HF_POSTGRES_TEST_URL`을 지정합니다. 이 환경변수가 없으면 테스트는 skip됩니다.

```bash
docker run --rm -d --name hf-pg-acceptance \
  -e POSTGRES_DB=harness_factory -e POSTGRES_USER=hf -e POSTGRES_PASSWORD=hf \
  -p 127.0.0.1:5433:5432 postgres:16
HF_POSTGRES_TEST_URL=postgresql+psycopg://hf:hf@127.0.0.1:5433/harness_factory \
  .venv/bin/pytest web/tests/test_postgres_acceptance.py -q
docker rm -f hf-pg-acceptance
```

### 2026-09-14 구현 검증 결과

- `.venv/bin/pytest web/tests -q`: **126 passed, 1 skipped**
  (skip은 `HF_POSTGRES_TEST_URL` 미설정 시의 PostgreSQL 인수 테스트입니다)
- `python3 -m unittest discover -s tests -v`: **143 tests, OK**
- `cd web/portal && npm test && npm run typecheck && npm run build`:
  **7 files / 24 tests passed**, typecheck 0 errors, Next.js production build 성공
- `docker compose config --quiet`: exit 0
- `alembic upgrade head` → `alembic downgrade base` 왕복과 `0004_published_channel`
  포워드 마이그레이션(중복 published 행 deprecate, partial unique index 생성/삭제)은
  `web/tests/test_schema.py`에서 검증합니다.
- `docker compose up --build -d` 후
  `curl --fail http://127.0.0.1:8000/api/health`는
  `{"ok":true,"service":"harness-factory-web","version":"1.1.0"}`를 반환했고,
  `curl --fail http://127.0.0.1:3000`은 HTTP 200을 반환했습니다.
- `docker compose exec api python -m web.acceptance.postgres_flow`는 실제
  PostgreSQL에 대해 create→validate→approve→build(실행 중인 worker가 처리)→
  asset/version→approve→publish→search→manifest와 cross-tenant 거부,
  unknown tenant 409까지 수행하고 `{"ok": true, ...}`를 반환했습니다.
- `HF_POSTGRES_TEST_URL`을 지정한 `web/tests/test_postgres_acceptance.py`도
  PostgreSQL 16 컨테이너에 대해 **1 passed**로 동일 흐름을 실행했습니다.
- `docker compose ps` 기준 서비스 상태:
  `postgres healthy`, `api healthy`, `portal healthy`, `worker Up`
- `web/tests/test_acceptance_flow.py`는 예제 design 생성 → validate → exact digest
  approval → build 1회 실행 → workflow asset/version 생성 → version exact digest
  approval → stable publish → developer manifest 조회 → cross-tenant 404 →
  audit sensitive-key 부재까지 통과했습니다.

- [승인된 설계](docs/superpowers/specs/2026-09-10-harness-factory-design.md)
- [구현 계획](docs/superpowers/plans/2026-09-10-harness-factory.md)
- [스킬 조립 규칙](.agents/skills/harness-factory/references/composition.md)

이 MVP는 상시 운영 플랫폼, 자동 배포, 신규 커넥터 생성이나 멀티런타임 지원을
포함하지 않습니다. 참고 영상의 전체 자막은 확보하지 못했으므로 영상의 세부
주장을 검증된 사실처럼 구현 근거로 사용하지 않았습니다.
