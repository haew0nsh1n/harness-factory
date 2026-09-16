---
title: Harness Factory CLI 워크플로
description: standalone core로 하네스를 생성하고 검사, 평가, 설치, 실행하는 방법
ms.date: 2026-09-16
ms.topic: how-to
---

## 개요

의존성 없는 standalone core는 별도 서버나 새 코딩 에이전트 없이 Copilot CLI용
하네스를 생성합니다. 프로젝트 스킬은 `.agents/skills/`를 사용하며 기존 MCP
서버와 CLI를 재사용합니다. 사용할 수 없는 연동은 담당자와 재개 조건이 있는
수동 단계로 남깁니다.

Python 3.9 이상과 GitHub Copilot CLI가 필요합니다. `gh`는 GitHub 연동에만
필요하며 패키지 생성과 오프라인 검사에는 인증이나 네트워크가 필요하지 않습니다.

## 인터뷰 시작

저장소 루트에서 Copilot CLI를 실행합니다.

```bash
copilot
```

다음과 같이 요청합니다.

> harness-factory 스킬을 사용해 고객 인터뷰를 시작해 줘.
> 고객은 Jira와 GitHub를 사용하고, 리뷰 단계의 반복 수정이 문제야.

팩토리 진입점은
[harness-factory 스킬](../.agents/skills/harness-factory/SKILL.md)입니다.
스킬 파일만 복사하지 말고 `harness_factory/`, `catalog/`, `examples/`를 포함한
전체 체크아웃에서 사용하세요. 고객에게는 생성된 패키지를 전달합니다.

인터뷰는 한 번에 한 질문을 합니다. 비밀번호, 토큰, 인증 쿠키는 받지 않습니다.
작업 자료는 Git에서 제외된 `.harness-factory/`에 보관하고 고객별 디렉터리를
분리합니다.

## 이슈 트래커 선택

인터뷰에서 하나의 source of truth를 확정합니다. 연결은 프로필에 고정되며 실행
중 자동 전환하지 않습니다.

* Git + Markdown은 `hf-issues-markdown`을 사용하고 `issues/<issue-id>.md`에
  저장합니다. 사용할 수 없으면 수동 단계로 전환합니다.
* GitHub Issues는 승인된 호환 스킬을 우선 사용하고 `mcp:github`를 대체 연결로
  사용합니다.
* Jira는 승인된 호환 스킬을 우선 사용하고 `mcp:jira`를 대체 연결로 사용합니다.

```bash
python3 -m harness_factory tracker-guide \
  --profile examples/github-issue/profile.json --target .
python3 -m harness_factory preflight --package PACKAGE
python3 -m harness_factory delivery-check --package PACKAGE
```

스킬 파일이나 MCP 이름의 존재만으로 provider 호환성, 인증, 권한, capability가
검증되지는 않습니다. 연결 방식을 바꾸려면 프로필을 다시 검토하고 패키지를
재생성해야 합니다. 자격 증명은 프로필이나 패키지에 저장하지 않습니다.

## 기본 스킬

* `hf-clarify`는 Matt Pocock의 `grilling`을 참고해 요구사항과 용어를 확인합니다.
* `hf-plan`은 Superpowers의 `writing-plans`를 참고해 승인된 요구를 계획합니다.
* `hf-tdd`는 Superpowers의 `test-driven-development`를 참고해 테스트 기반 구현을
  안내합니다.
* `hf-review`는 gstack의 `review`를 참고해 의도와 정확성을 검토합니다.
* `hf-manual`은 Matt Pocock의 `wizard`를 참고해 수동 인계를 명시합니다.
* `hf-issues-markdown`은 Matt Pocock의 `wizard`를 참고해 Git에서 이슈를
  추적합니다.

원본의 자동 시작 훅, 자동 업데이트, 브라우저와 텔레메트리 의존성은 포함하지
않습니다. 동일 역할의 프레임워크를 중복 활성화하지 않습니다. 출처, 라이선스,
호환성 근거는 [카탈로그](../catalog/catalog.json)에 기록되어 있습니다.

`verified`는
[읽기 전용 Copilot 모의 평가](evaluations/2026-09-10-copilot-skills.md)를 통과한
범위만 뜻합니다. 운영 인증이나 임의의 고객 워크플로까지 보장하지 않습니다.

## 예제 패키지 생성

예제는 실제 고객 데이터가 아니며 예제의 `approved` 값도 실제 승인을 대신하지
않습니다.

```bash
python3 -m harness_factory validate \
  --profile examples/github-issue/profile.json \
  --workflow examples/github-issue/workflow.json \
  --catalog catalog/catalog.json

DEMO=".harness-factory/demo-$(date +%Y%m%d-%H%M%S)-$$"
mkdir -p "$DEMO/customer"

python3 -m harness_factory generate \
  --profile examples/github-issue/profile.json \
  --workflow examples/github-issue/workflow.json \
  --scenarios examples/github-issue/scenarios.json \
  --catalog catalog/catalog.json \
  --output "$DEMO/package"

python3 -m harness_factory check --package "$DEMO/package"
```

생성기는 기존 출력 디렉터리를 덮어쓰지 않습니다. 전달 패키지에는 선택한 기본
스킬, 고객 규칙, 워크플로 진입 스킬, 명세, 실행 컨텍스트, 출처, 라이선스와
로컬 도구가 포함됩니다.

## 모의 평가와 전달 검사

구조 검사는 형식, 의존성, 참조, 승인과 실패 경로, 출처, 패키지 해시를
확인합니다. 구조 검사 통과는 에이전트 행동 검증을 뜻하지 않습니다.

에이전트 모의 평가는 실제 생성된 스킬에 가상 입력과 도구 결과를 제공하고 다음
상황의 응답을 기록합니다.

* 정상 인계와 승인 거절
* 연동 누락과 테스트 실패
* 중단 후 재개
* 불명확한 외부 쓰기 결과
* 지시문 삽입

평가 에이전트에는 쓰기 도구와 고객 인증을 제공하지 않습니다. 평가를 수행하지
못하면 패키지는 미검증 상태로 남습니다.

예제 결과를 사용할 때는 `package_manifest_sha256`를 생성된
`.harness/manifest.json`의 SHA-256으로 바꿔야 합니다. 체크인된 플레이스홀더는
검사에서 거절됩니다.

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

python3 -m harness_factory evaluate \
  --package "$DEMO/package" --results "$DEMO/results.json"
python3 -m harness_factory delivery-check --package "$DEMO/package"
```

`delivery-check`의 `ok: true`는 명령 실행 성공을 뜻합니다. 구현된 모든 전달
조건을 통과한 경우에만 `ready: true`가 됩니다. 기본 점검은 실행 파일 가용성만
확인하며 인증 네트워크 호출은 하지 않습니다. 승인한 읽기 전용 인증 점검은
명시적으로 활성화합니다.

```bash
python3 -m harness_factory delivery-check \
  --package "$DEMO/package" --allow-read-probes
```

자동 프로브는 알려진 GitHub 읽기 명령으로 제한됩니다. MCP와 지원하지 않는 도구는
수동 확인이 필요합니다. 일반 인증 성공은 특정 저장소 접근이나 쓰기 권한의
증거가 아닙니다.

## 설치

첫 설치 명령은 대상 파일을 바꾸지 않고 변경 내용과 승인 digest를 보여줍니다.

```bash
python3 -m harness_factory install \
  --package "$DEMO/package" --target "$DEMO/customer"
```

검토한 digest를 직접 전달해야 변경이 적용됩니다.

```bash
python3 -m harness_factory install \
  --package "$DEMO/package" --target "$DEMO/customer" \
  --approve "<승인한 미리보기의 digest 값>"
```

승인 후 패키지나 대상 파일이 달라지면 적용은 거절됩니다. digest는 변경 내용을
묶는 값이며 사람의 승인을 증명하는 서명은 아닙니다. 설치된 저장소를 배포 원본으로
재사용하지 말고 승인된 프로필과 명세에서 새 패키지를 생성하세요.

## 실행 기록과 재개

`record` 명령은 설치된 워크플로의 단계, 산출물, 승인과 수동 인계를 기록합니다.

```bash
python3 -m harness_factory record --help
python3 -m harness_factory record --package . --run issue-demo \
  --step clarify --status running
python3 -m harness_factory record --package . --run issue-demo \
  --step clarify --status awaiting-approval --evidence "작성한 초안의 위치"
python3 -m harness_factory record --package . --run issue-demo \
  --step clarify --status awaiting-approval \
  --decision approved --by product-owner --evidence "실제 승인 기록의 참조"
python3 -m harness_factory record --package . --run issue-demo \
  --step clarify --status completed --evidence "산출물 위치와 검증 근거"
```

외부 쓰기와 수동 단계는 행동 전 승인을 사용합니다. 결과가 불명확하면
`uncertain`으로 남기고 원래 작업의 결과를 확인하기 전에는 재실행하지 않습니다.
기록은 `.harness/runs/`에 저장됩니다.

이 기록은 실행 서버나 권한 강제 엔진이 아닙니다. Copilot 도구 허용 설정과 고객
시스템 권한을 별도로 제한해야 합니다.

## 고객별 구성

전체 필드 계약은 [스킬 계약](../.agents/skills/harness-factory/references/contracts.md)에
정의되어 있습니다.

* 승인된 워크플로 하나에 필요한 단계만 선택합니다.
* 단계 입력은 워크플로 입력이나 선행 단계의 산출물을 사용합니다.
* 도구 바인딩은 선언한 시스템의 `<id>.<capability>`만 사용합니다.
* 없는 연동은 담당자, 절차, 재개 조건이 있는 `manual` 단계로 만듭니다.
* 새 스킬은 출처 고정, 계약과 라이선스 검토, 모의 평가 후 등록합니다.
* 고객 시스템 접속 전 승인과 환경 준비를 별도로 확인합니다.
