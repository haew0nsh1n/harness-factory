"use client";

import {
  appendRow,
  NestedCard,
  ObjectListSection,
  removeRow,
  SelectField,
  StringListField,
  TextField,
  objectRows,
  replaceRow,
} from "@/components/studio/DesignFormFields";
import { updateDocumentField, type JsonDocument } from "@/lib/designForms";
import { useTranslations } from "@/i18n/I18nProvider";

const SCENARIO_STATES = [
  "awaiting-answer",
  "awaiting-approval",
  "awaiting-manual",
  "blocked",
  "cancelled",
  "failed",
  "uncertain",
  "completed",
] as const;

export function ScenarioForm({
  document,
  errors,
  onChange,
}: {
  document: JsonDocument;
  errors: Record<string, string>;
  onChange: (document: JsonDocument) => void;
}) {
  const t = useTranslations();
  const scenarios = objectRows(document.scenarios);
  return (
    <section className="workspace-panel structured-editor">
      <div className="section-header">
        <div>
          <p className="eyebrow">{t("profileForm.eyebrow")}</p>
          <h2>{t("scenarioForm.heading")}</h2>
        </div>
      </div>
      <SelectField
        label={t("scenarioForm.schemaVersion")}
        value={document.schema_version}
        options={["1"]}
        error={errors["scenarios.schema_version"]}
        onChange={(value) =>
          onChange(updateDocumentField(document, "schema_version", Number(value)))
        }
      />
      <div className="form-grid">
        <TextField label={t("scenarioForm.workflowId")} value={document.workflow} error={errors["scenarios.workflow"]} onChange={(value) => onChange(updateDocumentField(document, "workflow", value))} />
        <SelectField label={t("scenarioForm.mode")} value={document.mode} options={["read-only-agent-simulation"]} error={errors["scenarios.mode"]} onChange={(value) => onChange(updateDocumentField(document, "mode", value))} />
      </div>
      <ObjectListSection title={t("scenarioForm.section")} error={errors["scenarios.scenarios"]} onAdd={() => onChange(updateDocumentField(document, "scenarios", appendRow(document.scenarios, { id: "", given: "", expect: "blocked", forbidden: [] })))}>
        {scenarios.map(({ value: scenario, originalIndex: index }) => {
          const id = typeof scenario.id === "string" && scenario.id ? scenario.id : t("scenarioForm.fallback", { n: index + 1 });
          const updateScenario = (field: string, value: unknown) =>
            onChange(updateDocumentField(document, "scenarios", replaceRow(document.scenarios, index, updateDocumentField(scenario, field, value))));
          return (
            <NestedCard key={`scenario-${index}`} title={id} removeLabel={t("scenarioForm.remove", { id })} onRemove={() => onChange(updateDocumentField(document, "scenarios", removeRow(document.scenarios, index)))}>
              <TextField label={t("scenarioForm.id", { id })} value={scenario.id} error={errors[`scenarios.scenarios.${index}.id`]} onChange={(value) => updateScenario("id", value)} />
              <TextField multiline label={t("scenarioForm.given", { id })} value={scenario.given} error={errors[`scenarios.scenarios.${index}.given`]} onChange={(value) => updateScenario("given", value)} />
              <SelectField label={t("scenarioForm.expect", { id })} value={scenario.expect} options={SCENARIO_STATES} error={errors[`scenarios.scenarios.${index}.expect`]} onChange={(value) => updateScenario("expect", value)} />
              <StringListField label={t("scenarioForm.forbidden", { id })} value={scenario.forbidden} error={errors[`scenarios.scenarios.${index}.forbidden`]} onChange={(value) => updateScenario("forbidden", value)} />
            </NestedCard>
          );
        })}
      </ObjectListSection>
    </section>
  );
}
