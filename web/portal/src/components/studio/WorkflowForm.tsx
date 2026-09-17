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
import { FlowEditor } from "@/components/studio/FlowEditor";
import {
  analyzeDependencies,
  isJsonDocument,
  updateDocumentField,
  type JsonDocument,
} from "@/lib/designForms";
import { useTranslations } from "@/i18n/I18nProvider";

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
  const t = useTranslations();

  return (
    <section className="workspace-panel structured-editor">
      <div className="section-header">
        <div>
          <p className="eyebrow">{t("profileForm.eyebrow")}</p>
          <h2>{t("workflowForm.heading")}</h2>
        </div>
      </div>
      <SelectField
        label={t("workflowForm.schemaVersion")}
        value={document.schema_version}
        options={["1"]}
        error={errors["workflow.schema_version"]}
        onChange={(value) =>
          onChange(updateDocumentField(document, "schema_version", Number(value)))
        }
      />
      <div className="form-grid">
        {[
          ["id", "workflowForm.id"],
          ["name", "workflowForm.name"],
          ["customer_id", "workflowForm.customerId"],
          ["goal", "workflowForm.goal"],
          ["trigger", "workflowForm.trigger"],
        ].map(([field, labelKey]) => (
          <TextField
            key={field}
            label={t(labelKey)}
            value={document[field]}
            error={errors[`workflow.${field}`]}
            multiline={field === "goal" || field === "trigger"}
            onChange={(value) => onChange(updateDocumentField(document, field, value))}
          />
        ))}
      </div>
      <StringListField label={t("workflowForm.inputs")} value={document.inputs} error={errors["workflow.inputs"]} onChange={(value) => onChange(updateDocumentField(document, "inputs", value))} />
      <StringListField label={t("workflowForm.outputs")} value={document.outputs} error={errors["workflow.outputs"]} onChange={(value) => onChange(updateDocumentField(document, "outputs", value))} />
      <StringListField label={t("workflowForm.customerRules")} value={document.customer_rules} error={errors["workflow.customer_rules"]} onChange={(value) => onChange(updateDocumentField(document, "customer_rules", value))} />

      <FlowEditor
        title={t("workflowForm.stepsSection")}
        ariaLabel={t("workflowForm.stepsSection")}
        addLabel={t("formFields.addItem")}
        error={errors["workflow.steps"]}
        onAdd={() => onChange(updateDocumentField(document, "steps", appendRow(document.steps, { id: "", name: "", skill: skills[0] ?? "", needs: [], inputs: [], outputs: [], tools: [], effect: "read", approval: false, approval_timing: "before", approver: null, completion: "", failure: "", manual: null })))}
        items={steps.map(({ value: step, originalIndex: index }) => {
          const id = typeof step.id === "string" && step.id ? step.id : t("workflowForm.stepFallback", { n: index + 1 });
          const label = typeof step.name === "string" && step.name ? step.name : id;
          const manual = isJsonDocument(step.manual) ? step.manual : null;
          const updateStep = (field: string, value: unknown) =>
            onChange(updateDocumentField(document, "steps", replaceRow(document.steps, index, updateDocumentField(step, field, value))));
          return {
            key: `step-${index}`,
            label,
            removeLabel: t("workflowForm.stepRemove", { id }),
            onRemove: () => onChange(updateDocumentField(document, "steps", removeRow(document.steps, index))),
            content: (
              <>
                <div className="form-grid">
                  <TextField label={t("workflowForm.stepId", { id })} value={step.id} error={errors[`workflow.steps.${index}.id`]} onChange={(value) => updateStep("id", value)} />
                  <TextField label={t("workflowForm.stepName", { id })} value={step.name} error={errors[`workflow.steps.${index}.name`]} onChange={(value) => updateStep("name", value)} />
                  <SelectField label={t("workflowForm.stepSkill", { id })} value={step.skill} options={skills} error={errors[`workflow.steps.${index}.skill`]} onChange={(value) => updateStep("skill", value)} />
                  <SelectField label={t("workflowForm.stepEffect", { id })} value={step.effect} options={EFFECTS} error={errors[`workflow.steps.${index}.effect`]} onChange={(value) => updateStep("effect", value)} />
                </div>
                <StringListField label={t("workflowForm.stepNeeds", { id })} value={step.needs} error={errors[`workflow.steps.${index}.needs`]} onChange={(value) => updateStep("needs", value)} />
                <StringListField label={t("workflowForm.stepInputs", { id })} value={step.inputs} error={errors[`workflow.steps.${index}.inputs`]} onChange={(value) => updateStep("inputs", value)} />
                <StringListField label={t("workflowForm.stepOutputs", { id })} value={step.outputs} error={errors[`workflow.steps.${index}.outputs`]} onChange={(value) => updateStep("outputs", value)} />
                <StringListField label={t("workflowForm.stepTools", { id })} value={step.tools} error={errors[`workflow.steps.${index}.tools`]} onChange={(value) => updateStep("tools", value)} />
                <label className="choice-control">
                  <input type="checkbox" checked={step.approval === true} onChange={(event) => updateStep("approval", event.target.checked)} />
                  <span>{t("workflowForm.stepApprovalNeeded", { id })}</span>
                </label>
                {errors[`workflow.steps.${index}.approval`] ? <p className="field-error">{errors[`workflow.steps.${index}.approval`]}</p> : null}
                <div className="form-grid">
                  <SelectField label={t("workflowForm.stepApprovalTiming", { id })} value={step.approval_timing ?? "before"} options={APPROVAL_TIMINGS} error={errors[`workflow.steps.${index}.approval_timing`]} onChange={(value) => updateStep("approval_timing", value)} />
                  <SelectField label={t("workflowForm.stepApprovalRole", { id })} value={step.approver ?? ""} options={["", ...roles]} error={errors[`workflow.steps.${index}.approver`]} onChange={(value) => updateStep("approver", value || null)} />
                </div>
                <TextField multiline label={t("workflowForm.stepCompletion", { id })} value={step.completion} error={errors[`workflow.steps.${index}.completion`]} onChange={(value) => updateStep("completion", value)} />
                <TextField multiline label={t("workflowForm.stepFailure", { id })} value={step.failure} error={errors[`workflow.steps.${index}.failure`]} onChange={(value) => updateStep("failure", value)} />
                <label className="choice-control">
                  <input type="checkbox" checked={manual !== null} onChange={(event) => updateStep("manual", event.target.checked ? { owner: "", instructions: "", resume_when: "" } : null)} />
                  <span>{t("workflowForm.stepManualHandoff", { id })}</span>
                </label>
                {errors[`workflow.steps.${index}.manual`] ? <p className="field-error">{errors[`workflow.steps.${index}.manual`]}</p> : null}
                {manual ? (
                  <div className="form-grid">
                    <SelectField label={t("workflowForm.manualOwner", { id })} value={manual.owner} options={roles} error={errors[`workflow.steps.${index}.manual.owner`]} onChange={(value) => updateStep("manual", updateDocumentField(manual, "owner", value))} />
                    <TextField multiline label={t("workflowForm.manualInstructions", { id })} value={manual.instructions} error={errors[`workflow.steps.${index}.manual.instructions`]} onChange={(value) => updateStep("manual", updateDocumentField(manual, "instructions", value))} />
                    <TextField multiline label={t("workflowForm.manualResume", { id })} value={manual.resume_when} error={errors[`workflow.steps.${index}.manual.resume_when`]} onChange={(value) => updateStep("manual", updateDocumentField(manual, "resume_when", value))} />
                  </div>
                ) : null}
              </>
            ),
          };
        })}
      />

      <section className="dependency-preview" aria-label={t("workflowForm.dependencyAria")}>
        <strong>{t("workflowForm.dependencyTitle")}</strong>
        {analysis.missing.length === 0 && analysis.cycles.length === 0 ? (
          <p className="muted">{t("workflowForm.dependencyOk")}</p>
        ) : null}
        {analysis.missing.map((item) => <p className="error-text" key={`${item.stepId}-${item.dependencyId}`}>{t("workflowForm.missingNode", { stepId: item.stepId, dependencyId: item.dependencyId })}</p>)}
        {analysis.cycles.map((cycle) => <p className="error-text" key={cycle.join("-")}>{t("workflowForm.cycle", { cycle: cycle.join(" → ") })}</p>)}
      </section>

      <ObjectListSection title={t("workflowForm.traceabilitySection")} error={errors["workflow.traceability"]} onAdd={() => onChange(updateDocumentField(document, "traceability", appendRow(document.traceability, { requirement: "", steps: [], checks: [] })))}>
        {traceability.map(({ value: row, originalIndex: index }) => (
          <NestedCard key={`trace-${index}`} title={t("workflowForm.traceCard", { n: index + 1 })} removeLabel={t("workflowForm.traceRemove", { n: index + 1 })} onRemove={() => onChange(updateDocumentField(document, "traceability", removeRow(document.traceability, index)))}>
            <TextField multiline label={t("workflowForm.traceRequirement", { n: index + 1 })} value={row.requirement} error={errors[`workflow.traceability.${index}.requirement`]} onChange={(value) => onChange(updateDocumentField(document, "traceability", replaceRow(document.traceability, index, updateDocumentField(row, "requirement", value))))} />
            <StringListField label={t("workflowForm.traceSteps", { n: index + 1 })} value={row.steps} error={errors[`workflow.traceability.${index}.steps`]} onChange={(value) => onChange(updateDocumentField(document, "traceability", replaceRow(document.traceability, index, updateDocumentField(row, "steps", value))))} />
            <StringListField label={t("workflowForm.traceChecks", { n: index + 1 })} value={row.checks} error={errors[`workflow.traceability.${index}.checks`]} onChange={(value) => onChange(updateDocumentField(document, "traceability", replaceRow(document.traceability, index, updateDocumentField(row, "checks", value))))} />
          </NestedCard>
        ))}
      </ObjectListSection>
    </section>
  );
}
