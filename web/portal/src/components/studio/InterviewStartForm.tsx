"use client";

import { useTranslations } from "@/i18n/I18nProvider";
import type { InterviewStage } from "@/lib/types";

export const SELECTABLE_STAGES = [
  { id: "discovery", labelKey: "stages.discovery" },
  { id: "planning", labelKey: "stages.planning" },
  { id: "implementation", labelKey: "stages.implementation" },
  { id: "testing", labelKey: "stages.testing" },
  { id: "review", labelKey: "stages.review" },
  { id: "release", labelKey: "stages.release" },
  { id: "operations", labelKey: "stages.operations" },
] as const satisfies ReadonlyArray<{ id: Exclude<InterviewStage, "summary">; labelKey: string }>;

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
  const t = useTranslations();
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
          <span>{t("interviewStart.name")}</span>
          <input value={name} disabled={busy} onChange={(event) => onNameChange(event.target.value)} />
        </label>
        <label className="field">
          <span>{t("interviewStart.customerId")}</span>
          <input
            value={customerId}
            disabled={busy}
            onChange={(event) => onCustomerIdChange(event.target.value)}
            pattern="[a-z0-9][a-z0-9-]*"
          />
        </label>
      </div>
      <fieldset className="stage-selection">
        <legend>{t("interviewStart.stageLegend")}</legend>
        <p>{t("interviewStart.stageHint")}</p>
        <div className="actions-row">
          <button
            className="button-secondary button-compact"
            type="button"
            disabled={busy}
            onClick={() => onSelectedStagesChange(SELECTABLE_STAGES.map((stage) => stage.id))}
          >
            {t("interviewStart.selectAll")}
          </button>
          <button
            className="button-secondary button-compact"
            type="button"
            disabled={busy}
            onClick={() => onSelectedStagesChange([])}
          >
            {t("interviewStart.deselect")}
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
              <span>{t(stage.labelKey)}</span>
            </label>
          ))}
        </div>
      </fieldset>
      <div className="privacy-notice">
        <h2>{t("interviewStart.privacyHeading")}</h2>
        <p>{t("interviewStart.privacyBody1")}</p>
        <p>{t("interviewStart.privacyBody2")}</p>
        <label className="consent-check">
          <input
            type="checkbox"
            checked={consented}
            disabled={busy}
            onChange={(event) => onConsentChange(event.target.checked)}
          />
          <span>{t("interviewStart.consent")}</span>
        </label>
      </div>
      <button
        className="button-primary"
        type="button"
        disabled={!consented || selectedStages.length === 0 || busy}
        onClick={onStart}
      >
        {t("interviewStart.start")}
      </button>
      {selectedStages.length === 0 ? <p className="field-error">{t("interviewStart.minStage")}</p> : null}
      {error ? <p className="error-text" role="alert">{error}</p> : null}
    </section>
  );
}
