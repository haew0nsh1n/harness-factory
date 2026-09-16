---
title: Harness Factory 운영 가이드
description: 로컬 Compose 스택, 인증 경계, 데이터 보존과 인수 검증 절차
ms.date: 2026-09-16
ms.topic: reference
---

## Compose 스택

로컬 프로덕션형 스택은 루트의 `docker-compose.yml`로 실행합니다.

```bash
docker compose up --build
open http://localhost:3000
```

구성 서비스는 다음과 같습니다.

* `postgres`는 PostgreSQL 16과 `postgres-data` volume을 사용하며 internal
  network에만 연결됩니다.
* `api`는 Alembic migration과 개발 tenant bootstrap 후 FastAPI를 실행합니다.
* `worker`는 `hf-artifacts` volume을 공유하고 외부 egress 없이 빌드를 처리합니다.
* `portal`은 Next.js 포털을 호스트의 `127.0.0.1:3000`에 게시합니다.

API는 호스트의 `127.0.0.1:8000`에만 게시됩니다. worker에는 Docker socket이나
호스트 저장소를 마운트하지 않습니다.

```bash
docker compose ps
curl --fail http://127.0.0.1:8000/api/health
curl --fail http://127.0.0.1:3000
```

## 기업 패키지 피드

Compose 이미지는 `python:3.12-slim`에서 `uv==0.8.3`과 격리 빌드용
`setuptools==80.9.0`을 부트스트랩합니다.

`uv sync --frozen`은 잠금 파일에 기록된 URL을 그대로 사용합니다.
`PIP_INDEX_URL`이나 `UV_INDEX_URL`만 바꿔도 기존 잠금 파일의 소스는 바뀌지
않습니다. 기업 피드가 필요하면 같은 패키지 버전으로 별도 잠금 파일을 만듭니다.

```bash
uv --version
python3 scripts/prepare_uv_lock.py \
  --index-url https://packages.example.test/pypi/simple \
  --output uv.enterprise.lock

PIP_INDEX_URL=https://packages.example.test/pypi/simple \
UV_LOCK_FILE=uv.enterprise.lock \
docker compose up --build
```

준비 스크립트는 모든 패키지 이름과 버전이 기본 `uv.lock`과 같은지 확인합니다.
피드 접근이나 버전 일치에 실패하면 다른 소스로 전환하지 않습니다.

인덱스 URL은 자격 증명, query, fragment가 없는 HTTPS URL이어야 합니다. 토큰,
사용자명, 비밀번호를 URL, 잠금 파일, build argument, 저장소 설정에 넣지 마세요.

## 개발 tenant bootstrap

Compose는 개발 조직, subject membership과 네 개의 한국어 예제 design을
자동으로 준비합니다. 수동으로 다시 확인할 때는 다음 명령을 사용합니다.

```bash
docker compose exec api python -m web.api.organizations.bootstrap \
  --with-sample-designs
```

bootstrap은 멱등입니다. 누락된 샘플만 추가하며 기존 design의 이름, 본문, 상태,
digest, revision, timestamp를 변경하지 않습니다. 다른 tenant의 데이터도
수정하지 않습니다.

다음 조건이 아니면 명령은 실행을 거절합니다.

```text
HF_AUTH_MODE=development
HF_ALLOW_INSECURE_DEVELOPMENT_AUTH=true
```

샘플은 편집용 초안입니다. fixture의 `workflow.approved` metadata는 고객 승인,
평가 완료, 배포 준비 상태를 뜻하지 않습니다.

## 인증 경계

개발 인증은 검증되지 않은 신원 헤더를 사용하므로 명시적 opt-in과 loopback
바인딩을 요구합니다. 포털 서버 프록시가 개발 신원 헤더를 control-plane 요청에만
추가합니다.

운영 환경은 다음 구성이 필요합니다.

* NextAuth Microsoft Entra provider를 사용하는 포털 로그인
* tenant, audience, 만료를 검증하는 API bearer token 검증
* Entra subject를 애플리케이션 조직 membership과 역할에 매핑
* Registry API delegated scope와 사용자 동의
* Azure OpenAI용 managed identity와 별도 inference RBAC

이 저장소는 Entra 앱 등록, 역할 부여, Azure 리소스 생성, 사용자 동의를 자동으로
수행하지 않습니다. CLI나 요청 인수의 조직과 역할은 운영 권한으로 사용하지
않습니다.

## 인터뷰 데이터와 모델 경계

인터뷰는 사용자가 동의한 뒤에만 저장되고 Azure OpenAI로 전송됩니다. 기본 보존
기간은 마지막 쓰기 활동부터 30일이며 `HF_INTERVIEW_RETENTION_DAYS`로 설정합니다.

```bash
uv run --frozen --no-config python -m web.api.interviews.cleanup
```

인터뷰 삭제는 대화, 작업, 제안을 제거하지만 이미 생성된 design은 제거하지
않습니다. 데이터베이스 백업 보존 기간은 별도로 관리해야 합니다.

비밀, 소스 코드, 이슈 본문, 고객 connector credential을 인터뷰에 입력하지
마세요. 알려진 비밀 패턴은 저장과 모델 호출 전에 거절하지만 모든 민감 정보를
탐지한다고 보장하지 않습니다.

현재 모델 경계는 다음과 같습니다.

* 답변 길이 8,000자
* 세션 길이 60턴
* 전체 모델 문맥 64,000자
* draft 출력 최대 8,192 token
* 전체 요청 60초
* 전체 deadline 내 일시 오류 재시도 최대 1회

한도를 넘으면 문맥을 조용히 생략하지 않고 오류를 반환합니다.

## 게시와 설치 경계

design 검토, build, version 검토, 게시와 폐기는 현재 digest를 요구합니다. 오래된
digest나 잘못된 SHA-256 형식은 거절됩니다.

asset과 channel 조합에는 하나의 published 버전만 존재합니다. 새 버전을 게시하면
이전 버전은 같은 트랜잭션에서 `deprecated`가 되며 이력은 유지됩니다. artifact는
API와 worker가 공유하는 immutable key 아래 저장됩니다.

CLI는 `login`, `search`, `info`, `install`, `logout`을 제공합니다. `upgrade`와
사용 telemetry는 현재 구현하지 않았습니다. 설치 성공은 evaluation이나 고객 환경
readiness를 뜻하지 않습니다.

## PostgreSQL 인수

실행 중인 Compose 스택에서 전체 lifecycle과 tenant 격리를 검사합니다.

```bash
docker compose up --build -d
docker compose exec api python -m web.acceptance.postgres_flow
```

이 흐름은 create, validate, approve, build, version approve, publish, search,
manifest와 cross-tenant 거절을 실제 PostgreSQL에서 확인합니다.

호스트 pytest로 실행하려면 별도 PostgreSQL을 준비하고 SQLAlchemy 형식의
`HF_POSTGRES_TEST_URL`을 지정합니다. 환경 변수가 없으면 PostgreSQL opt-in
테스트는 skip됩니다.

```bash
HF_POSTGRES_TEST_URL=postgresql+psycopg://hf:hf@127.0.0.1:5433/harness_factory \
  uv run --frozen --no-config --extra test --extra cli \
  pytest web/tests/test_interview_acceptance.py \
    web/tests/test_postgres_acceptance.py -q
```

## 배포 패키지 인수

wheel 기반 CLI 인수는 새 가상 환경에 실제 wheel과 선언된 의존성을 설치합니다.
runner의 checkout이나 site-packages를 우회 연결하지 않습니다.

```bash
uv run --frozen --no-config --extra test --extra cli \
  pytest tests/cli/test_packaging.py \
    web/tests/test_distribution_acceptance.py -q
```

승인된 피드나 완전한 wheelhouse를 명시할 수 있습니다.

```bash
HF_ACCEPTANCE_INDEX_URL=https://packages.example.test/pypi/simple \
  uv run --frozen --no-config --extra test --extra cli \
  pytest tests/cli/test_packaging.py \
    web/tests/test_distribution_acceptance.py -q

HF_ACCEPTANCE_WHEELHOUSE=/absolute/path/to/wheelhouse \
  uv run --frozen --no-config --extra test --extra cli \
  pytest tests/cli/test_packaging.py \
    web/tests/test_distribution_acceptance.py -q
```

## 검증 범위

기본 테스트는 합성 모델과 deterministic fake model을 사용해 인터뷰, 설계 교체,
canonical validation, digest 승인, build, publish, 실제 wheel 설치, 고객 파일
보존과 tenant 격리를 검증합니다.

Playwright visual 테스트는 control-plane 응답을 가로채므로 실제 API와 데이터베이스
성공의 증거로 사용하지 않습니다. 별도 integration 테스트는 브라우저, Next.js
proxy, FastAPI와 격리된 SQLite를 연결합니다.

다음 항목은 로컬 인수 범위 밖입니다.

* 실제 운영 Entra 브라우저 로그인과 앱 등록
* Azure-hosted managed identity와 RBAC
* 실제 고객 입력, 저장소와 connector
* 실제 고객 환경 readiness
* 운영용 행동 평가 영수증
