"use client";

import { useEffect, useMemo, useRef, useState } from "react";

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
  isJsonDocument,
  updateDocumentField,
  type JsonDocument,
} from "@/lib/designForms";

const TRACKER_PROVIDERS = ["markdown", "github", "jira"] as const;
const TRACKER_CONNECTIONS = ["local", "skill", "mcp"] as const;
const TRACKER_CAPABILITIES = [
  "issue-read",
  "issue-create",
  "issue-update",
  "issue-transition",
  "issue-comment",
] as const;
const EMPTY_DOCUMENT: JsonDocument = {};

interface ProfileFormProps {
  document: JsonDocument;
  errors: Record<string, string>;
  onChange: (document: JsonDocument) => void;
  onTransientStateChange?: (state: {
    dirty: boolean;
    errors: Record<string, string>;
  }) => void;
}

interface GlossaryRow {
  id: number;
  originalTerm: string;
  pendingTerm: string;
}

export function ProfileForm({
  document,
  errors,
  onChange,
  onTransientStateChange,
}: ProfileFormProps) {
  const sdlc = objectRows(document.sdlc);
  const pains = objectRows(document.pains);
  const facts = objectRows(document.facts);
  const systems = objectRows(document.systems);
  const tracker = isJsonDocument(document.issue_tracker)
    ? document.issue_tracker
    : {};
  const canonicalGlossary = isJsonDocument(document.glossary)
    ? document.glossary
    : EMPTY_DOCUMENT;
  const glossary = Object.entries(canonicalGlossary);
  const nextGlossaryRowId = useRef(0);
  const [glossaryRows, setGlossaryRows] = useState<GlossaryRow[]>(() =>
    glossary.map(([term]) => ({
      id: nextGlossaryRowId.current++,
      originalTerm: term,
      pendingTerm: term,
    })),
  );
  const provider = typeof tracker.provider === "string" ? tracker.provider : "";
  const connection = typeof tracker.connection === "string" ? tracker.connection : "";

  useEffect(() => {
    const terms = glossary.map(([term]) => term);
    setGlossaryRows((current) =>
      terms.map((term) => {
        const exact = current.find((row) => row.originalTerm === term);
        if (exact) {
          return exact;
        }
        const committed = current.find(
          (row) =>
            row.pendingTerm === term && !terms.includes(row.originalTerm),
        );
        if (committed) {
          return { ...committed, originalTerm: term, pendingTerm: term };
        }
        return {
          id: nextGlossaryRowId.current++,
          originalTerm: term,
          pendingTerm: term,
        };
      }),
    );
  }, [document.glossary]);

  const glossaryKeyErrors = useMemo(
    () =>
      glossaryRows.reduce<Record<string, string>>((result, row, index) => {
        if (!row.pendingTerm.trim()) {
          result[`profile.glossary.${index}.term`] = "용어를 입력하세요.";
        } else if (
          row.pendingTerm !== row.originalTerm &&
          (Object.prototype.hasOwnProperty.call(
            canonicalGlossary,
            row.pendingTerm,
          ) ||
            glossaryRows.some(
              (candidate) =>
                candidate.id !== row.id &&
                candidate.pendingTerm === row.pendingTerm,
            ))
        ) {
          result[`profile.glossary.${index}.term`] =
            "이미 존재하는 용어입니다. 기존 정의를 덮어쓰지 않았습니다.";
        }
        return result;
      }, {}),
    [canonicalGlossary, glossaryRows],
  );
  const glossaryKeyDirty = glossaryRows.some(
    (row) => row.pendingTerm !== row.originalTerm,
  );

  useEffect(() => {
    onTransientStateChange?.({
      dirty: glossaryKeyDirty,
      errors: glossaryKeyErrors,
    });
  }, [glossaryKeyDirty, glossaryKeyErrors, onTransientStateChange]);

  function commitGlossaryTerm(row: GlossaryRow): void {
    const rowIndex = glossaryRows.findIndex((candidate) => candidate.id === row.id);
    if (rowIndex < 0 || glossaryKeyErrors[`profile.glossary.${rowIndex}.term`]) {
      return;
    }
    const currentRow = glossaryRows[rowIndex];
    if (!currentRow || currentRow.pendingTerm === currentRow.originalTerm) {
      return;
    }
    const next = Object.fromEntries(glossary);
    if (
      Object.prototype.hasOwnProperty.call(next, currentRow.pendingTerm) &&
      currentRow.pendingTerm !== currentRow.originalTerm
    ) {
      return;
    }
    const definition = next[currentRow.originalTerm];
    delete next[currentRow.originalTerm];
    next[currentRow.pendingTerm] = definition;
    onChange(updateDocumentField(document, "glossary", next));
  }

  function updateTracker(field: string, value: unknown): void {
    onChange(
      updateDocumentField(
        document,
        "issue_tracker",
        updateDocumentField(tracker, field, value),
      ),
    );
  }

  return (
    <section className="workspace-panel structured-editor">
      <div className="section-header">
        <div>
          <p className="eyebrow">구조화된 양식</p>
          <h2>고객 프로필</h2>
        </div>
      </div>
      <SelectField
        label="프로필 스키마 버전"
        value={document.schema_version}
        options={["1"]}
        error={errors["profile.schema_version"]}
        onChange={(value) =>
          onChange(updateDocumentField(document, "schema_version", Number(value)))
        }
      />
      <div className="form-grid">
        <TextField
          label="고객 ID"
          value={document.customer_id}
          error={errors["profile.customer_id"]}
          onChange={(value) => onChange(updateDocumentField(document, "customer_id", value))}
        />
        <TextField
          label="고객 이름"
          value={document.name}
          error={errors["profile.name"]}
          onChange={(value) => onChange(updateDocumentField(document, "name", value))}
        />
      </div>

      <ObjectListSection
        title="SDLC 현재 및 희망 프로세스"
        error={errors["profile.sdlc"]}
        onAdd={() =>
          onChange(updateDocumentField(document, "sdlc", appendRow(document.sdlc, { stage: "", current: "", desired: "" })))
        }
      >
        {sdlc.map(({ value: row, originalIndex: index }) => (
          <NestedCard
            key={`sdlc-${index}`}
            title={`단계 ${index + 1}`}
            removeLabel={`SDLC 단계 ${index + 1} 삭제`}
            onRemove={() => onChange(updateDocumentField(document, "sdlc", removeRow(document.sdlc, index)))}
          >
            <TextField label={`SDLC 단계 ${index + 1} 이름`} value={row.stage} error={errors[`profile.sdlc.${index}.stage`]} onChange={(value) => onChange(updateDocumentField(document, "sdlc", replaceRow(document.sdlc, index, updateDocumentField(row, "stage", value))))} />
            <TextField multiline label={`SDLC 단계 ${index + 1} 현재 프로세스`} value={row.current} error={errors[`profile.sdlc.${index}.current`]} onChange={(value) => onChange(updateDocumentField(document, "sdlc", replaceRow(document.sdlc, index, updateDocumentField(row, "current", value))))} />
            <TextField multiline label={`SDLC 단계 ${index + 1} 희망 프로세스`} value={row.desired} error={errors[`profile.sdlc.${index}.desired`]} onChange={(value) => onChange(updateDocumentField(document, "sdlc", replaceRow(document.sdlc, index, updateDocumentField(row, "desired", value))))} />
          </NestedCard>
        ))}
      </ObjectListSection>

      <ObjectListSection
        title="용어집"
        error={errors["profile.glossary"]}
        onAdd={() =>
          onChange(updateDocumentField(document, "glossary", { ...Object.fromEntries(glossary), "": "" }))
        }
      >
        {glossaryRows.map((row, index) => {
          const definition = isJsonDocument(document.glossary)
            ? document.glossary[row.originalTerm]
            : undefined;
          return (
          <NestedCard
            key={row.id}
            title={`용어 ${index + 1}`}
            removeLabel={`용어 ${index + 1} 삭제`}
            onRemove={() => {
              const next = Object.fromEntries(glossary);
              delete next[row.originalTerm];
              onChange(updateDocumentField(document, "glossary", next));
            }}
          >
            <TextField
              label={`용어 ${index + 1} 키`}
              value={row.pendingTerm}
              error={
                glossaryKeyErrors[`profile.glossary.${index}.term`] ??
                errors[`profile.glossary.${index}.term`]
              }
              onChange={(value) => {
                setGlossaryRows((current) =>
                  current.map((candidate) =>
                    candidate.id === row.id
                      ? { ...candidate, pendingTerm: value }
                      : candidate,
                  ),
                );
              }}
              onBlur={() => commitGlossaryTerm(row)}
            />
            <TextField
              multiline
              label={`용어 ${index + 1} 정의`}
              value={definition}
              error={errors[`profile.glossary.${row.originalTerm}`]}
              onChange={(value) =>
                onChange(
                  updateDocumentField(document, "glossary", {
                    ...Object.fromEntries(glossary),
                    [row.originalTerm]: value,
                  }),
                )
              }
            />
          </NestedCard>
          );
        })}
      </ObjectListSection>

      <StringListField label="역할" value={document.roles} error={errors["profile.roles"]} onChange={(value) => onChange(updateDocumentField(document, "roles", value))} />

      <ObjectListSection title="문제와 영향" error={errors["profile.pains"]} onAdd={() => onChange(updateDocumentField(document, "pains", appendRow(document.pains, { description: "", impact: "", frequency: "" })))}>
        {pains.map(({ value: row, originalIndex: index }) => (
          <NestedCard key={`pain-${index}`} title={`문제 ${index + 1}`} removeLabel={`문제 ${index + 1} 삭제`} onRemove={() => onChange(updateDocumentField(document, "pains", removeRow(document.pains, index)))}>
            <TextField multiline label={`문제 ${index + 1} 설명`} value={row.description} error={errors[`profile.pains.${index}.description`]} onChange={(value) => onChange(updateDocumentField(document, "pains", replaceRow(document.pains, index, updateDocumentField(row, "description", value))))} />
            <TextField multiline label={`문제 ${index + 1} 영향`} value={row.impact} error={errors[`profile.pains.${index}.impact`]} onChange={(value) => onChange(updateDocumentField(document, "pains", replaceRow(document.pains, index, updateDocumentField(row, "impact", value))))} />
            <TextField label={`문제 ${index + 1} 빈도`} value={row.frequency} error={errors[`profile.pains.${index}.frequency`]} onChange={(value) => onChange(updateDocumentField(document, "pains", replaceRow(document.pains, index, updateDocumentField(row, "frequency", value))))} />
          </NestedCard>
        ))}
      </ObjectListSection>

      <StringListField label="성공 기준" value={document.success_criteria} error={errors["profile.success_criteria"]} onChange={(value) => onChange(updateDocumentField(document, "success_criteria", value))} />
      <StringListField label="제약" value={document.constraints} error={errors["profile.constraints"]} onChange={(value) => onChange(updateDocumentField(document, "constraints", value))} />

      <ObjectListSection title="사실과 근거" error={errors["profile.facts"]} onAdd={() => onChange(updateDocumentField(document, "facts", appendRow(document.facts, { id: "", statement: "", evidence: "" })))}>
        {facts.map(({ value: row, originalIndex: index }) => (
          <NestedCard key={`fact-${index}`} title={`사실 ${index + 1}`} removeLabel={`사실 ${index + 1} 삭제`} onRemove={() => onChange(updateDocumentField(document, "facts", removeRow(document.facts, index)))}>
            <TextField label={`사실 ${index + 1} ID`} value={row.id} error={errors[`profile.facts.${index}.id`]} onChange={(value) => onChange(updateDocumentField(document, "facts", replaceRow(document.facts, index, updateDocumentField(row, "id", value))))} />
            <TextField multiline label={`사실 ${index + 1} 내용`} value={row.statement} error={errors[`profile.facts.${index}.statement`]} onChange={(value) => onChange(updateDocumentField(document, "facts", replaceRow(document.facts, index, updateDocumentField(row, "statement", value))))} />
            <TextField multiline label={`사실 ${index + 1} 근거`} value={row.evidence} error={errors[`profile.facts.${index}.evidence`]} onChange={(value) => onChange(updateDocumentField(document, "facts", replaceRow(document.facts, index, updateDocumentField(row, "evidence", value))))} />
          </NestedCard>
        ))}
      </ObjectListSection>

      <StringListField label="가정" value={document.assumptions} error={errors["profile.assumptions"]} onChange={(value) => onChange(updateDocumentField(document, "assumptions", value))} />
      <StringListField label="미확인 항목" value={document.unknowns} error={errors["profile.unknowns"]} onChange={(value) => onChange(updateDocumentField(document, "unknowns", value))} />

      <ObjectListSection title="시스템과 도구 역량" error={errors["profile.systems"]} onAdd={() => onChange(updateDocumentField(document, "systems", appendRow(document.systems, { id: "", kind: "", tool: "", capabilities: [] })))}>
        {systems.map(({ value: row, originalIndex: index }) => (
          <NestedCard key={`system-${index}`} title={`시스템 ${index + 1}`} removeLabel={`시스템 ${index + 1} 삭제`} onRemove={() => onChange(updateDocumentField(document, "systems", removeRow(document.systems, index)))}>
            <TextField label={`시스템 ${index + 1} ID`} value={row.id} error={errors[`profile.systems.${index}.id`]} onChange={(value) => onChange(updateDocumentField(document, "systems", replaceRow(document.systems, index, updateDocumentField(row, "id", value))))} />
            <TextField label={`시스템 ${index + 1} 종류`} value={row.kind} error={errors[`profile.systems.${index}.kind`]} onChange={(value) => onChange(updateDocumentField(document, "systems", replaceRow(document.systems, index, updateDocumentField(row, "kind", value))))} />
            <TextField label={`시스템 ${index + 1} 도구 토큰`} value={row.tool} error={errors[`profile.systems.${index}.tool`]} onChange={(value) => onChange(updateDocumentField(document, "systems", replaceRow(document.systems, index, updateDocumentField(row, "tool", value))))} />
            <StringListField label={`시스템 ${index + 1} 역량`} value={row.capabilities} error={errors[`profile.systems.${index}.capabilities`]} onChange={(value) => onChange(updateDocumentField(document, "systems", replaceRow(document.systems, index, updateDocumentField(row, "capabilities", value))))} />
          </NestedCard>
        ))}
      </ObjectListSection>

      <section className="nested-form-section">
        <h3>이슈 트래커</h3>
        {errors["profile.issue_tracker"] ? <p className="field-error">{errors["profile.issue_tracker"]}</p> : null}
        <div className="form-grid">
          <SelectField label="이슈 트래커 시스템" value={tracker.system_id} options={systems.flatMap(({ value: system }) => typeof system.id === "string" ? [system.id] : [])} error={errors["profile.issue_tracker.system_id"]} onChange={(value) => updateTracker("system_id", value)} />
          <SelectField label="이슈 트래커 제공자" value={tracker.provider} options={TRACKER_PROVIDERS} error={errors["profile.issue_tracker.provider"]} onChange={(value) => updateTracker("provider", value)} />
          <SelectField label="이슈 트래커 연결" value={tracker.connection} options={TRACKER_CONNECTIONS} error={errors["profile.issue_tracker.connection"]} onChange={(value) => updateTracker("connection", value)} />
          <TextField label="이슈 트래커 프로젝트" value={tracker.project} error={errors["profile.issue_tracker.project"]} onChange={(value) => updateTracker("project", value)} />
          {provider === "markdown" ? <TextField label="이슈 파일 경로" value={tracker.path} error={errors["profile.issue_tracker.path"]} onChange={(value) => updateTracker("path", value || null)} /> : null}
          {connection === "skill" ? <TextField label="이슈 트래커 스킬" value={tracker.skill} error={errors["profile.issue_tracker.skill"]} onChange={(value) => updateTracker("skill", value || null)} /> : null}
          {connection === "mcp" || connection === "skill" ? <TextField label="이슈 트래커 MCP" value={tracker.mcp} error={errors["profile.issue_tracker.mcp"]} onChange={(value) => updateTracker("mcp", value || null)} /> : null}
        </div>
        <div className="choice-grid" aria-label="이슈 트래커 역량">
          {TRACKER_CAPABILITIES.map((capability) => {
            const selected = Array.isArray(tracker.capabilities) && tracker.capabilities.includes(capability);
            return (
              <label className="choice-control" key={capability}>
                <input
                  type="checkbox"
                  checked={selected}
                  onChange={(event) => {
                    const current = Array.isArray(tracker.capabilities)
                      ? tracker.capabilities
                      : [];
                    updateTracker(
                      "capabilities",
                      event.target.checked
                        ? [...current, capability]
                        : current.filter((item) => item !== capability),
                    );
                  }}
                />
                <span>{capability}</span>
              </label>
            );
          })}
        </div>
        {errors["profile.issue_tracker.capabilities"] ? <p className="field-error">{errors["profile.issue_tracker.capabilities"]}</p> : null}
      </section>
    </section>
  );
}
