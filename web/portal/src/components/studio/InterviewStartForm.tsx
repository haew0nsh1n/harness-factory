"use client";

import type { InterviewStage } from "@/lib/types";

export const SELECTABLE_STAGES = [
  { id: "discovery", label: "발견" },
  { id: "planning", label: "계획" },
  { id: "implementation", label: "구현" },
  { id: "testing", label: "테스트" },
  { id: "review", label: "검토" },
  { id: "release", label: "릴리스" },
  { id: "operations", label: "운영" },
] as const satisfies ReadonlyArray<{ id: Exclude<InterviewStage, "summary">; label: string }>;

export const DEFAULT_SELECTED_STAGES = [
  "planning",
  "implementation",
  "review",
] as const;

interface InterviewStartFormProps {
  name: string;
  customerId: string;
  consented: boolean;
  selectedStages: string[];
  busy: boolean;
  error: string | null;
  onNameChange: (value: string) => void;
  onCustomerIdChange: (value: string) => void;
  onConsentChange: (value: boolean) => void;
  onSelectedStagesChange: (value: string[]) => void;
  onStart: () => void;
}

export function InterviewStartForm({
  name,
  customerId,
  consented,
  selectedStages,
  busy,
  error,
  onNameChange,
  onCustomerIdChange,
  onConsentChange,
  onSelectedStagesChange,
  onStart,
}: InterviewStartFormProps) {
  const selected = new Set(selectedStages);

  function toggleStage(id: string, checked: boolean): void {
    onSelectedStagesChange(
      checked
        ? SELECTABLE_STAGES.filter((stage) => selected.has(stage.id) || stage.id === id).map(
            (stage) => stage.id,
          )
        : selectedStages.filter((stage) => stage !== id),
    );
  }

  return (
    <section className="workspace-panel consent-panel" aria-busy={busy}>
      <div className="form-grid">
        <label className="field">
          <span>인터뷰 이름</span>
          <input value={name} disabled={busy} onChange={(event) => onNameChange(event.target.value)} />
        </label>
        <label className="field">
          <span>고객 ID</span>
          <input
            value={customerId}
            disabled={busy}
            onChange={(event) => onCustomerIdChange(event.target.value)}
            pattern="[a-z0-9][a-z0-9-]*"
          />
        </label>
      </div>
      <fieldset className="stage-selection">
        <legend>인터뷰할 SDLC 단계</legend>
        <p>필요한 단계만 선택하세요. 선택하지 않은 단계는 인터뷰 진행에 포함하지 않습니다.</p>
        <div className="actions-row">
          <button
            className="button-secondary button-compact"
            type="button"
            disabled={busy}
            onClick={() => onSelectedStagesChange(SELECTABLE_STAGES.map((stage) => stage.id))}
          >
            모두 선택
          </button>
          <button
            className="button-secondary button-compact"
            type="button"
            disabled={busy}
            onClick={() => onSelectedStagesChange([])}
          >
            선택 해제
          </button>
        </div>
        <div className="choice-grid">
          {SELECTABLE_STAGES.map((stage) => (
            <label className="choice-control" key={stage.id}>
              <input
                type="checkbox"
                checked={selected.has(stage.id)}
                disabled={busy}
                onChange={(event) => toggleStage(stage.id, event.target.checked)}
              />
              <span>{stage.label}</span>
            </label>
          ))}
        </div>
      </fieldset>
      <div className="privacy-notice">
        <h2>전송 및 보존 확인</h2>
        <p>
          작성한 인터뷰 텍스트는 구성된 Azure OpenAI 배포로 전송되며 Responses 요청은 store:
          false로 처리됩니다. 인터뷰와 확인한 근거는 조직 범위 데이터베이스에 마지막 활동부터
          30일간 보존됩니다.
        </p>
        <p>
          인터뷰 삭제는 대화와 미적용 제안을 제거하지만 이미 만든 설계는 삭제하지 않습니다.
          비밀, 자격 증명, 소스 코드, 저장소 파일 또는 이슈 본문을 입력하지 마세요.
        </p>
        <label className="consent-check">
          <input
            type="checkbox"
            checked={consented}
            disabled={busy}
            onChange={(event) => onConsentChange(event.target.checked)}
          />
          <span>Azure OpenAI 전송과 30일 보존·삭제 동작을 이해하고 인터뷰 시작에 동의합니다.</span>
        </label>
      </div>
      <button
        className="button-primary"
        type="button"
        disabled={!consented || selectedStages.length === 0 || busy}
        onClick={onStart}
      >
        인터뷰 시작
      </button>
      {selectedStages.length === 0 ? <p className="field-error">최소 한 개의 SDLC 단계를 선택하세요.</p> : null}
      {error ? <p className="error-text" role="alert">{error}</p> : null}
    </section>
  );
}
