# 개발용 샘플 워크플로

이 디렉터리의 네 샘플은 가상의 고객과 아직 확인되지 않은 실행 환경을 전제로 한
편집 가능한 초안이다. `workflow.approved` 값은 필수 스키마를 만족시키기 위한
고정된 가상 fixture 작성자와 시각이며, 고객 승인이나 실행 승인을 뜻하지 않는다.
bootstrap은 항상 design을 `draft` revision 1로만 저장하고 Approval, Build,
Registry 또는 Evaluation 레코드를 만들지 않는다. 실제 사용 전에는 현재 catalog로
validate하고, 정확한 digest를 확인한 별도 reviewer 승인이 필요하다.

각 디렉터리의 `profile.json`, `workflow.json`, `scenarios.json`은 CLI validator에
직접 재사용할 수 있으며, catalog는 저장소의 `catalog/catalog.json` 전체를 사용한다.
