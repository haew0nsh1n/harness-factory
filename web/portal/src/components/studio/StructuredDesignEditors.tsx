"use client";

import { useMemo } from "react";
import { ProfileForm } from "@/components/studio/ProfileForm";
import { ScenarioForm } from "@/components/studio/ScenarioForm";
import { WorkflowForm } from "@/components/studio/WorkflowForm";
import {
  validateDesignFormDocuments,
  type DesignFormErrors,
  type JsonDocument,
} from "@/lib/designForms";

export interface DesignDocuments {
  profile: JsonDocument;
  workflow: JsonDocument;
  scenarios: JsonDocument;
  catalog: JsonDocument;
}

interface StructuredDesignEditorsProps {
  documents: DesignDocuments;
  authoritativeCatalog: JsonDocument | null;
  onChange: (documents: DesignDocuments) => void;
  errors?: DesignFormErrors;
  findings?: string[];
  readOnly?: boolean;
  onTransientStateChange?: (state: {
    dirty: boolean;
    errors: DesignFormErrors;
  }) => void;
}

function documentFindings(findings: string[], prefix: string): string[] {
  return findings.filter((finding) => {
    const path = finding.split(":", 1)[0]?.trim();
    return path === prefix;
  });
}

function findingsByKnownPath(
  findings: string[],
  errors: DesignFormErrors,
): DesignFormErrors {
  const result = { ...errors };
  findings.forEach((finding) => {
    const path = finding.split(":", 1)[0]?.trim();
    if (path && isKnownFormPath(path)) {
      result[path] = result[path] ? `${result[path]} ${finding}` : finding;
    }
  });
  return result;
}

function isKnownFormPath(path: string): boolean {
  return /^(profile\.(customer_id|name|sdlc(?:\.\d+\.(stage|current|desired))?|glossary(?:\..+)?|roles|pains(?:\.\d+\.(description|impact|frequency))?|success_criteria|constraints|facts(?:\.\d+\.(id|statement|evidence))?|assumptions|unknowns|systems(?:\.\d+\.(id|kind|tool|capabilities))?|issue_tracker(?:\.(system_id|provider|connection|project|path|skill|mcp|capabilities))?)|workflow\.(id|name|customer_id|goal|trigger|inputs|outputs|customer_rules|steps(?:\.\d+\.(id|name|skill|needs|inputs|outputs|tools|effect|approval|approval_timing|approver|completion|failure|manual(?:\.(owner|instructions|resume_when))?))?|traceability(?:\.\d+\.(requirement|steps|checks))?)|scenarios\.(workflow|mode|scenarios(?:\.\d+\.(id|given|expect|forbidden))?))$/.test(path);
}

function FindingBlock({
  findings,
  prefix,
}: {
  findings: string[];
  prefix: string;
}) {
  const matches = documentFindings(findings, prefix);
  if (matches.length === 0) {
    return null;
  }
  return (
    <div className="mapped-findings" aria-label={`${prefix} 검증 결과`}>
      {matches.map((finding) => (
        <pre className="finding-text" key={finding}>
          {finding}
        </pre>
      ))}
    </div>
  );
}

function ReadOnlyDocument({
  label,
  document,
}: {
  label: string;
  document: JsonDocument;
}) {
  return (
    <section className="workspace-panel structured-editor">
      <p className="eyebrow">전체 문서 검토</p>
      <h2>{label}</h2>
      <textarea
        className="readonly-json readonly-json-textarea"
        aria-label={`${label} 전체 JSON 검토`}
        value={JSON.stringify(document, null, 2)}
        readOnly
        rows={18}
        spellCheck={false}
      />
    </section>
  );
}

export function StructuredDesignEditors({
  documents,
  authoritativeCatalog,
  onChange,
  errors: suppliedErrors,
  findings = [],
  readOnly = false,
  onTransientStateChange,
}: StructuredDesignEditorsProps) {
  const computedErrors = useMemo(
    () =>
      validateDesignFormDocuments(
        documents,
        authoritativeCatalog ?? documents.catalog,
      ),
    [authoritativeCatalog, documents],
  );
  const errors = suppliedErrors ?? computedErrors;
  const displayedErrors = useMemo(
    () => findingsByKnownPath(findings, errors),
    [errors, findings],
  );

  if (readOnly) {
    return (
      <div className="structured-editors">
        <p className="readonly-notice">
          이 제안은 다이제스트 검토용 읽기 전용입니다. 각 전체 JSON 문서는
          키보드로 초점을 옮겨 스크롤하고 복사할 수 있습니다.
        </p>
        <ReadOnlyDocument label="프로필" document={documents.profile} />
        <ReadOnlyDocument label="워크플로" document={documents.workflow} />
        <ReadOnlyDocument label="시나리오" document={documents.scenarios} />
        <ReadOnlyDocument label="승인 카탈로그" document={documents.catalog} />
        {findings.length > 0 ? (
          <section className="workspace-panel" aria-label="원문 검증 결과">
            <p className="eyebrow">원문 검증 결과</p>
            {findings.map((finding) => (
              <pre className="finding-text" key={finding}>
                {finding}
              </pre>
            ))}
          </section>
        ) : null}
      </div>
    );
  }

  const unplacedFindings = findings.filter((finding) => {
    const path = finding.split(":", 1)[0]?.trim();
    return (
      path !== "profile" &&
      path !== "workflow" &&
      path !== "scenarios" &&
      path !== "catalog" &&
      !(path && isKnownFormPath(path))
    );
  });

  return (
    <div className="structured-editors">
      <FindingBlock findings={findings} prefix="profile" />
      <ProfileForm
        document={documents.profile}
        errors={displayedErrors}
        onChange={(profile) => onChange({ ...documents, profile })}
        onTransientStateChange={onTransientStateChange}
      />
      <FindingBlock findings={findings} prefix="workflow" />
      <WorkflowForm
        document={documents.workflow}
        profile={documents.profile}
        catalog={authoritativeCatalog}
        errors={displayedErrors}
        onChange={(workflow) => onChange({ ...documents, workflow })}
      />
      <FindingBlock findings={findings} prefix="scenarios" />
      <ScenarioForm
        document={documents.scenarios}
        errors={displayedErrors}
        onChange={(scenarios) => onChange({ ...documents, scenarios })}
      />
      <FindingBlock findings={findings} prefix="catalog" />
      <section className="workspace-panel structured-editor">
        <p className="eyebrow">서버 소유</p>
        <h2>승인 카탈로그</h2>
        <pre className="readonly-json" tabIndex={0} aria-label="서버 승인 카탈로그">
          {JSON.stringify(authoritativeCatalog ?? documents.catalog, null, 2)}
        </pre>
      </section>
      {unplacedFindings.length > 0 ? (
        <section className="workspace-panel" aria-label="매핑되지 않은 검증 결과">
          <p className="eyebrow">원문 검증 결과</p>
          {unplacedFindings.map((finding) => (
            <pre className="finding-text" key={finding}>
              {finding}
            </pre>
          ))}
        </section>
      ) : null}
    </div>
  );
}
