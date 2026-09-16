---
title: Harness Factory 개발 가이드
description: 웹 플랫폼과 배포 CLI를 로컬에서 개발하고 검증하는 방법
ms.date: 2026-09-16
ms.topic: how-to
---

## 요구 사항

웹 애플리케이션과 배포 CLI 개발 환경은 Python 3.12, 고정된 `uv.lock`, Node.js와
npm을 사용합니다. Docker Compose로 전체 스택을 실행할 수도 있습니다.

## Python 환경

```bash
uv sync --frozen --no-config --extra test --extra cli
uv run --frozen --no-config python -m harness_factory --help
uv run --frozen --no-config --extra cli hf --help
```

`uv.lock`은 공개 PyPI 소스와 정확한 아티팩트 해시를 기록합니다. `--no-config`는
사용자나 머신 전역 uv 설정이 기본 소스를 암묵적으로 바꾸지 못하게 합니다.

## 웹 포털

API와 데이터베이스를 실행한 뒤 포털 개발 서버를 시작합니다.

```bash
cd web/portal
npm install
NEXT_PUBLIC_HF_AUTH_MODE=development \
HF_API_BASE_URL=http://127.0.0.1:8000 \
HF_DEV_ORGANIZATION=local-dev \
HF_DEV_SUBJECT=portal-dev \
HF_DEV_ROLES=author,reviewer,registry-admin,developer,org-admin \
npm run dev -- --hostname 127.0.0.1 --port 3000
```

개발 신원은 브라우저가 아니라 Next.js 서버 프록시가 control-plane 요청에
추가합니다. API와 포털을 loopback 외부에 공개하지 마세요.

전체 로컬 스택은 루트에서 실행할 수 있습니다.

```bash
docker compose up --build
open http://localhost:3000
```

## Azure OpenAI 인터뷰

로컬에서 실제 Azure OpenAI 인터뷰를 개발할 때는 API를 호스트에서 실행합니다.
SDK는 `DefaultAzureCredential`로 인증합니다. API 키, Key Vault, 수동 credential
선택은 지원하지 않습니다.

```bash
az login
mkdir -p .harness-factory
export HF_DATABASE_URL=sqlite+pysqlite:///.harness-factory/host-api.db
export HF_AZURE_OPENAI_ENDPOINT=https://<resource>.cognitiveservices.azure.com/
export HF_AZURE_OPENAI_DEPLOYMENT=<deployment-name>
export HF_AUTH_MODE=development
export HF_ALLOW_INSECURE_DEVELOPMENT_AUTH=true

uv run --frozen --no-config alembic upgrade head
uv run --frozen --no-config python -m web.api.organizations.bootstrap \
  --with-sample-designs
uv run --frozen --no-config uvicorn web.api.main:create_app \
  --factory --host 127.0.0.1 --port 8000
```

호스팅 환경에서 특정 user-assigned managed identity를 선택해야 할 때만
`HF_AZURE_MANAGED_IDENTITY_CLIENT_ID`를 설정합니다. 개발자 토큰을 환경 변수로
복사하거나 `~/.azure`를 컨테이너에 마운트하지 마세요.

설정이 없으면 authoring과 registry 기능은 동작하지만 인터뷰 추론은
`llm_not_configured`로 비활성화됩니다. 로컬 Azure CLI 인증은 운영 Entra 로그인이나
호스팅된 managed identity 접근의 증거가 아닙니다.

## 배포 CLI

`hf`는 게시된 워크플로를 검색하고 검증된 패키지를 설치합니다. standalone
`python -m harness_factory` 진입점은 별도로 유지됩니다.

```bash
uv run --frozen --no-config --extra cli hf login \
  --registry https://registry.example.test \
  --tenant <entra-tenant-id> \
  --client-id <public-client-application-id> \
  --scope api://<registry-api-app-id>/registry.access
uv run --frozen --no-config --extra cli hf search issue --json
uv run --frozen --no-config --extra cli hf info issue-to-pr@1.0.0
uv run --frozen --no-config --extra cli hf install issue-to-pr@1.0.0 \
  --target ../customer-repository
uv run --frozen --no-config --extra cli hf install issue-to-pr@1.0.0 \
  --target ../customer-repository --approve <preview-digest>
uv run --frozen --no-config --extra cli hf logout
```

첫 `hf install`은 변경을 적용하지 않고 파일 작업, 제한된 로컬 diff, 승인 digest를
출력합니다. 적용 시 Registry 게시 상태, delivery metadata, 캐시 바이트와 대상
상태를 다시 확인합니다. SHA-256은 metadata와 다운로드 바이트를 결합하지만
publisher 서명을 대신하지 않습니다.

개발 인증은 loopback IP origin과 명시적 `--development`를 함께 요구합니다.

```bash
uv run --frozen --no-config --extra cli hf login \
  --registry http://127.0.0.1:8000 --development \
  --organization local-dev --subject developer-1 --role developer
```

운영 로그인에는 device code flow가 허용된 Microsoft Entra public-client 앱,
Registry API delegated scope와 조직 membership이 필요합니다. 토큰 캐시는 지원되는
네이티브 OS keyring에만 저장됩니다. plaintext 또는 임의 플러그인 keyring은
거절됩니다.

## wheel 빌드

```bash
uv build --wheel
python3.12 -m venv .harness-factory/cli-smoke
.harness-factory/cli-smoke/bin/python -m pip install \
  'dist/harness_factory-1.1.0-py3-none-any.whl[cli]'
(cd .harness-factory && cli-smoke/bin/hf --help)
```

새 환경에 `[cli]` extra를 설치하려면 HTTPS PyPI나 승인된 동일 버전 패키지 피드에
접속할 수 있어야 합니다.

## 테스트

가장 작은 관련 테스트부터 실행합니다.

```bash
uv run --frozen --no-config --extra test --extra cli pytest
uv run --frozen --no-config python -m unittest discover -s tests -v

cd web/portal
npm test
npm run typecheck
npm run build
npm run test:e2e:integration
```

PostgreSQL과 배포 인수 절차는 [운영 가이드](operations.md)를 참고하세요.
