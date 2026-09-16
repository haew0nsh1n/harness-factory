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
  const scenarios = objectRows(document.scenarios);
  return (
    <section className="workspace-panel structured-editor">
      <div className="section-header">
        <div>
          <p className="eyebrow">구조화된 양식</p>
          <h2>시나리오</h2>
        </div>
      </div>
      <SelectField
        label="시나리오 스키마 버전"
        value={document.schema_version}
        options={["1"]}
        error={errors["scenarios.schema_version"]}
        onChange={(value) =>
          onChange(updateDocumentField(document, "schema_version", Number(value)))
        }
      />
      <div className="form-grid">
        <TextField label="시나리오 워크플로 ID" value={document.workflow} error={errors["scenarios.workflow"]} onChange={(value) => onChange(updateDocumentField(document, "workflow", value))} />
        <SelectField label="시나리오 실행 모드" value={document.mode} options={["read-only-agent-simulation"]} error={errors["scenarios.mode"]} onChange={(value) => onChange(updateDocumentField(document, "mode", value))} />
      </div>
      <ObjectListSection title="검증 시나리오" error={errors["scenarios.scenarios"]} onAdd={() => onChange(updateDocumentField(document, "scenarios", appendRow(document.scenarios, { id: "", given: "", expect: "blocked", forbidden: [] })))}>
        {scenarios.map(({ value: scenario, originalIndex: index }) => {
          const id = typeof scenario.id === "string" && scenario.id ? scenario.id : `시나리오-${index + 1}`;
          const updateScenario = (field: string, value: unknown) =>
            onChange(updateDocumentField(document, "scenarios", replaceRow(document.scenarios, index, updateDocumentField(scenario, field, value))));
          return (
            <NestedCard key={`scenario-${index}`} title={id} removeLabel={`${id} 시나리오 삭제`} onRemove={() => onChange(updateDocumentField(document, "scenarios", removeRow(document.scenarios, index)))}>
              <TextField label={`${id} 시나리오 ID`} value={scenario.id} error={errors[`scenarios.scenarios.${index}.id`]} onChange={(value) => updateScenario("id", value)} />
              <TextField multiline label={`${id} 시나리오 조건`} value={scenario.given} error={errors[`scenarios.scenarios.${index}.given`]} onChange={(value) => updateScenario("given", value)} />
              <SelectField label={`${id} 시나리오 예상 상태`} value={scenario.expect} options={SCENARIO_STATES} error={errors[`scenarios.scenarios.${index}.expect`]} onChange={(value) => updateScenario("expect", value)} />
              <StringListField label={`${id} 시나리오 금지 동작`} value={scenario.forbidden} error={errors[`scenarios.scenarios.${index}.forbidden`]} onChange={(value) => updateScenario("forbidden", value)} />
            </NestedCard>
          );
        })}
      </ObjectListSection>
    </section>
  );
}
