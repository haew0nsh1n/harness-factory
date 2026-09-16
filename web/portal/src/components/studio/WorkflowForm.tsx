"use client";

import { useMemo } from "react";

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
import {
  analyzeDependencies,
  isJsonDocument,
  updateDocumentField,
  type JsonDocument,
} from "@/lib/designForms";

const EFFECTS = ["read", "local", "external-write", "manual"] as const;
const APPROVAL_TIMINGS = ["before", "after"] as const;

function catalogSkills(catalog: JsonDocument | null): string[] {
  return objectRows(catalog?.skills).flatMap(({ value: entry }) =>
    typeof entry.id === "string" ? [entry.id] : [],
  );
}

export function WorkflowForm({
  document,
  profile,
  catalog,
  errors,
  onChange,
}: {
  document: JsonDocument;
  profile: JsonDocument;
  catalog: JsonDocument | null;
  errors: Record<string, string>;
  onChange: (document: JsonDocument) => void;
}) {
  const steps = objectRows(document.steps);
  const traceability = objectRows(document.traceability);
  const skills = catalogSkills(catalog);
  const roles = Array.isArray(profile.roles)
    ? profile.roles.filter((item): item is string => typeof item === "string")
    : [];
  const analysis = useMemo(() => analyzeDependencies(document), [document]);

  return (
    <section className="workspace-panel structured-editor">
      <div className="section-header">
        <div>
          <p className="eyebrow">구조화된 양식</p>
          <h2>워크플로</h2>
        </div>
      </div>
      <SelectField
        label="워크플로 스키마 버전"
        value={document.schema_version}
        options={["1"]}
        error={errors["workflow.schema_version"]}
        onChange={(value) =>
          onChange(updateDocumentField(document, "schema_version", Number(value)))
        }
      />
      <div className="form-grid">
        {[
          ["id", "워크플로 ID"],
          ["name", "워크플로 이름"],
          ["customer_id", "워크플로 고객 ID"],
          ["goal", "워크플로 목표"],
          ["trigger", "워크플로 트리거"],
        ].map(([field, label]) => (
          <TextField
            key={field}
            label={label}
            value={document[field]}
            error={errors[`workflow.${field}`]}
            multiline={field === "goal" || field === "trigger"}
            onChange={(value) => onChange(updateDocumentField(document, field, value))}
          />
        ))}
      </div>
      <StringListField label="워크플로 입력" value={document.inputs} error={errors["workflow.inputs"]} onChange={(value) => onChange(updateDocumentField(document, "inputs", value))} />
      <StringListField label="워크플로 출력" value={document.outputs} error={errors["workflow.outputs"]} onChange={(value) => onChange(updateDocumentField(document, "outputs", value))} />
      <StringListField label="고객 규칙" value={document.customer_rules} error={errors["workflow.customer_rules"]} onChange={(value) => onChange(updateDocumentField(document, "customer_rules", value))} />

      <ObjectListSection title="워크플로 단계" error={errors["workflow.steps"]} onAdd={() => onChange(updateDocumentField(document, "steps", appendRow(document.steps, { id: "", name: "", skill: skills[0] ?? "", needs: [], inputs: [], outputs: [], tools: [], effect: "read", approval: false, approval_timing: "before", approver: null, completion: "", failure: "", manual: null })))}>
        {steps.map(({ value: step, originalIndex: index }) => {
          const id = typeof step.id === "string" && step.id ? step.id : `단계-${index + 1}`;
          const manual = isJsonDocument(step.manual) ? step.manual : null;
          const updateStep = (field: string, value: unknown) =>
            onChange(updateDocumentField(document, "steps", replaceRow(document.steps, index, updateDocumentField(step, field, value))));
          return (
            <NestedCard key={`step-${index}`} title={`${id} 단계`} removeLabel={`${id} 단계 삭제`} onRemove={() => onChange(updateDocumentField(document, "steps", removeRow(document.steps, index)))}>
              <div className="form-grid">
                <TextField label={`${id} 단계 ID`} value={step.id} error={errors[`workflow.steps.${index}.id`]} onChange={(value) => updateStep("id", value)} />
                <TextField label={`${id} 단계 이름`} value={step.name} error={errors[`workflow.steps.${index}.name`]} onChange={(value) => updateStep("name", value)} />
                <SelectField label={`${id} 단계 승인 스킬`} value={step.skill} options={skills} error={errors[`workflow.steps.${index}.skill`]} onChange={(value) => updateStep("skill", value)} />
                <SelectField label={`${id} 단계 효과`} value={step.effect} options={EFFECTS} error={errors[`workflow.steps.${index}.effect`]} onChange={(value) => updateStep("effect", value)} />
              </div>
              <StringListField label={`${id} 단계 선행 단계`} value={step.needs} error={errors[`workflow.steps.${index}.needs`]} onChange={(value) => updateStep("needs", value)} />
              <StringListField label={`${id} 단계 입력`} value={step.inputs} error={errors[`workflow.steps.${index}.inputs`]} onChange={(value) => updateStep("inputs", value)} />
              <StringListField label={`${id} 단계 출력`} value={step.outputs} error={errors[`workflow.steps.${index}.outputs`]} onChange={(value) => updateStep("outputs", value)} />
              <StringListField label={`${id} 단계 도구`} value={step.tools} error={errors[`workflow.steps.${index}.tools`]} onChange={(value) => updateStep("tools", value)} />
              <label className="choice-control">
                <input type="checkbox" checked={step.approval === true} onChange={(event) => updateStep("approval", event.target.checked)} />
                <span>{id} 단계 승인 필요</span>
              </label>
              {errors[`workflow.steps.${index}.approval`] ? <p className="field-error">{errors[`workflow.steps.${index}.approval`]}</p> : null}
              <div className="form-grid">
                <SelectField label={`${id} 단계 승인 시점`} value={step.approval_timing ?? "before"} options={APPROVAL_TIMINGS} error={errors[`workflow.steps.${index}.approval_timing`]} onChange={(value) => updateStep("approval_timing", value)} />
                <SelectField label={`${id} 단계 승인 역할`} value={step.approver ?? ""} options={["", ...roles]} error={errors[`workflow.steps.${index}.approver`]} onChange={(value) => updateStep("approver", value || null)} />
              </div>
              <TextField multiline label={`${id} 단계 완료 조건`} value={step.completion} error={errors[`workflow.steps.${index}.completion`]} onChange={(value) => updateStep("completion", value)} />
              <TextField multiline label={`${id} 단계 실패 처리`} value={step.failure} error={errors[`workflow.steps.${index}.failure`]} onChange={(value) => updateStep("failure", value)} />
              <label className="choice-control">
                <input type="checkbox" checked={manual !== null} onChange={(event) => updateStep("manual", event.target.checked ? { owner: "", instructions: "", resume_when: "" } : null)} />
                <span>{id} 단계 수동 인계</span>
              </label>
              {errors[`workflow.steps.${index}.manual`] ? <p className="field-error">{errors[`workflow.steps.${index}.manual`]}</p> : null}
              {manual ? (
                <div className="form-grid">
                  <SelectField label={`${id} 수동 인계 담당 역할`} value={manual.owner} options={roles} error={errors[`workflow.steps.${index}.manual.owner`]} onChange={(value) => updateStep("manual", updateDocumentField(manual, "owner", value))} />
                  <TextField multiline label={`${id} 수동 인계 지침`} value={manual.instructions} error={errors[`workflow.steps.${index}.manual.instructions`]} onChange={(value) => updateStep("manual", updateDocumentField(manual, "instructions", value))} />
                  <TextField multiline label={`${id} 수동 인계 재개 조건`} value={manual.resume_when} error={errors[`workflow.steps.${index}.manual.resume_when`]} onChange={(value) => updateStep("manual", updateDocumentField(manual, "resume_when", value))} />
                </div>
              ) : null}
            </NestedCard>
          );
        })}
      </ObjectListSection>

      <section className="dependency-preview" aria-label="의존성 그래프 미리보기">
        <strong>실제 의존성 그래프</strong>
        {analysis.edges.length === 0 ? <p className="muted">needs 간선이 없습니다.</p> : (
          <ul>{analysis.edges.map((edge, index) => <li key={`${edge.from}-${edge.to}-${index}`}><code>{edge.from}</code> → <code>{edge.to}</code></li>)}</ul>
        )}
        {analysis.missing.map((item) => <p className="error-text" key={`${item.stepId}-${item.dependencyId}`}>{item.stepId} 단계가 없는 노드 {item.dependencyId}에 의존합니다.</p>)}
        {analysis.cycles.map((cycle) => <p className="error-text" key={cycle.join("-")}>순환 의존성: {cycle.join(" → ")}</p>)}
      </section>

      <ObjectListSection title="추적성 검사" error={errors["workflow.traceability"]} onAdd={() => onChange(updateDocumentField(document, "traceability", appendRow(document.traceability, { requirement: "", steps: [], checks: [] })))}>
        {traceability.map(({ value: row, originalIndex: index }) => (
          <NestedCard key={`trace-${index}`} title={`추적성 ${index + 1}`} removeLabel={`추적성 ${index + 1} 삭제`} onRemove={() => onChange(updateDocumentField(document, "traceability", removeRow(document.traceability, index)))}>
            <TextField multiline label={`추적성 ${index + 1} 요구사항`} value={row.requirement} error={errors[`workflow.traceability.${index}.requirement`]} onChange={(value) => onChange(updateDocumentField(document, "traceability", replaceRow(document.traceability, index, updateDocumentField(row, "requirement", value))))} />
            <StringListField label={`추적성 ${index + 1} 단계`} value={row.steps} error={errors[`workflow.traceability.${index}.steps`]} onChange={(value) => onChange(updateDocumentField(document, "traceability", replaceRow(document.traceability, index, updateDocumentField(row, "steps", value))))} />
            <StringListField label={`추적성 ${index + 1} 검사`} value={row.checks} error={errors[`workflow.traceability.${index}.checks`]} onChange={(value) => onChange(updateDocumentField(document, "traceability", replaceRow(document.traceability, index, updateDocumentField(row, "checks", value))))} />
          </NestedCard>
        ))}
      </ObjectListSection>
    </section>
  );
}
