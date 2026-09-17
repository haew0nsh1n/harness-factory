"use client";

import { useMemo } from "react";
import { DebugJsonDisclosure } from "@/components/studio/DebugJsonDisclosure";
import { DesignDocumentReview } from "@/components/studio/DesignDocumentReview";
import { ProfileForm } from "@/components/studio/ProfileForm";
import { ScenarioForm } from "@/components/studio/ScenarioForm";
import { WorkflowForm } from "@/components/studio/WorkflowForm";
import { useTranslations } from "@/i18n/I18nProvider";
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

export type DesignDocumentKey = keyof DesignDocuments;

interface StructuredDesignEditorsProps {
  documents: DesignDocuments;
  authoritativeCatalog: JsonDocument | null;
  onChange: (documents: DesignDocuments) => void;
  errors?: DesignFormErrors;
  findings?: string[];
  readOnly?: boolean;
  // Render only one document's editor (for the tabbed studio layout).
  only?: DesignDocumentKey;
  onTransientStateChange?: (state: {
    dirty: boolean;
    errors: DesignFormErrors;
  }) => void;
}

const ADVISORY_FINDING_CODES = new Set([
  "unconfirmed-model-fact",
  "unconfirmed-fact",
  "scope-confirmation-required",
  "scope-not-selected",
  "scope-mismatch",
]);

function findingParts(finding: string): {
  path: string;
  code: string;
  message: string;
} {
  const segments = finding.split(":");
  return {
    path: (segments[0] ?? "").trim(),
    code: (segments[1] ?? "").trim(),
    message: segments.slice(2).join(":").trim(),
  };
}

function isAdvisoryFinding(finding: string): boolean {
  return ADVISORY_FINDING_CODES.has(findingParts(finding).code);
}

// Drop the repeated "path:" prefix so a section does not restate it per line.
function findingDisplay(finding: string): string {
  const { code, message } = findingParts(finding);
  return code ? `${code}: ${message}` : message;
}

function documentFindings(findings: string[], prefix: string): string[] {
  return findings.filter((finding) => findingParts(finding).path === prefix);
}

function findingsByKnownPath(
  findings: string[],
  errors: DesignFormErrors,
): DesignFormErrors {
  const result = { ...errors };
  findings.forEach((finding) => {
    const { path } = findingParts(finding);
    if (path && isKnownFormPath(path)) {
      const line = findingDisplay(finding);
      result[path] = result[path] ? `${result[path]}\n${line}` : line;
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
  const t = useTranslations();
  const matches = documentFindings(findings, prefix);
  if (matches.length === 0) {
    return null;
  }
  return (
    <div className="mapped-findings" aria-label={t("structuredEditors.findingAria", { prefix })}>
      {matches.map((finding) => (
        <pre className="finding-text" key={finding}>
          {findingDisplay(finding)}
        </pre>
      ))}
    </div>
  );
}

function AdvisoryNotes({ findings }: { findings: string[] }) {
  const t = useTranslations();
  if (findings.length === 0) {
    return null;
  }
  return (
    <section
      className="workspace-panel advisory-notes"
      aria-label={t("structuredEditors.advisoryNotes")}
    >
      <p className="eyebrow">{t("structuredEditors.advisoryNotes")}</p>
      <p className="muted">{t("structuredEditors.advisoryHint")}</p>
      <ul className="advisory-note-list">
        {findings.map((finding) => (
          <li className="advisory-note" key={finding}>
            {findingParts(finding).message}
          </li>
        ))}
      </ul>
    </section>
  );
}

function ReadOnlyDocument({
  label,
  document,
}: {
  label: string;
  document: JsonDocument;
}) {
  const t = useTranslations();
  return (
    <section className="workspace-panel structured-editor">
      <p className="eyebrow">{t("structuredEditors.fullReview")}</p>
      <h2>{label}</h2>
      <textarea
        className="readonly-json readonly-json-textarea"
        aria-label={t("structuredEditors.fullJsonAria", { label })}
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
  only,
  onTransientStateChange,
}: StructuredDesignEditorsProps) {
  const t = useTranslations();
  const computedErrors = useMemo(
    () =>
      validateDesignFormDocuments(
        documents,
        authoritativeCatalog ?? documents.catalog,
        t,
      ),
    [authoritativeCatalog, documents, t],
  );
  const errors = suppliedErrors ?? computedErrors;
  const advisoryFindings = useMemo(
    () => findings.filter(isAdvisoryFinding),
    [findings],
  );
  const actionableFindings = useMemo(
    () => findings.filter((finding) => !isAdvisoryFinding(finding)),
    [findings],
  );
  const displayedErrors = useMemo(
    () => findingsByKnownPath(actionableFindings, errors),
    [errors, actionableFindings],
  );

  if (readOnly) {
    return (
      <div className="structured-editors">
        <p className="readonly-notice">{t("structuredEditors.readOnlyNotice")}</p>
        <DesignDocumentReview documents={documents} />
        <DebugJsonDisclosure>
          <ReadOnlyDocument label={t("structuredEditors.profile")} document={documents.profile} />
          <ReadOnlyDocument label={t("structuredEditors.workflow")} document={documents.workflow} />
          <ReadOnlyDocument label={t("structuredEditors.scenarios")} document={documents.scenarios} />
          <ReadOnlyDocument label={t("structuredEditors.approvalCatalog")} document={documents.catalog} />
        </DebugJsonDisclosure>
        <AdvisoryNotes findings={advisoryFindings} />
        {actionableFindings.length > 0 ? (
          <section className="workspace-panel" aria-label={t("structuredEditors.rawFindings")}>
            <p className="eyebrow">{t("structuredEditors.rawFindings")}</p>
            {actionableFindings.map((finding) => (
              <pre className="finding-text" key={finding}>
                {findingDisplay(finding)}
              </pre>
            ))}
          </section>
        ) : null}
      </div>
    );
  }

  const unplacedFindings = actionableFindings.filter((finding) => {
    const { path } = findingParts(finding);
    return (
      path !== "profile" &&
      path !== "workflow" &&
      path !== "scenarios" &&
      path !== "catalog" &&
      !(path && isKnownFormPath(path))
    );
  });

  const shows = (key: DesignDocumentKey) => !only || only === key;
  const advisoryForView = only
    ? advisoryFindings.filter((finding) =>
        findingParts(finding).path.startsWith(only),
      )
    : advisoryFindings;

  return (
    <div className="structured-editors">
      <AdvisoryNotes findings={advisoryForView} />
      {shows("profile") ? (
        <>
          <FindingBlock findings={actionableFindings} prefix="profile" />
          <ProfileForm
            document={documents.profile}
            errors={displayedErrors}
            onChange={(profile) => onChange({ ...documents, profile })}
            onTransientStateChange={onTransientStateChange}
          />
        </>
      ) : null}
      {shows("workflow") ? (
        <>
          <FindingBlock findings={actionableFindings} prefix="workflow" />
          <WorkflowForm
            document={documents.workflow}
            profile={documents.profile}
            catalog={authoritativeCatalog}
            errors={displayedErrors}
            onChange={(workflow) => onChange({ ...documents, workflow })}
          />
        </>
      ) : null}
      {shows("scenarios") ? (
        <>
          <FindingBlock findings={actionableFindings} prefix="scenarios" />
          <ScenarioForm
            document={documents.scenarios}
            errors={displayedErrors}
            onChange={(scenarios) => onChange({ ...documents, scenarios })}
          />
        </>
      ) : null}
      {shows("catalog") ? (
        <>
          <FindingBlock findings={actionableFindings} prefix="catalog" />
          <DesignDocumentReview
            documents={{
              ...documents,
              catalog: authoritativeCatalog ?? documents.catalog,
            }}
            documentTypes={["catalog"]}
          />
          <DebugJsonDisclosure
            label={t("structuredEditors.catalogRawLabel")}
            hint={t("structuredEditors.catalogRawHint")}
          >
            <ReadOnlyDocument
              label={t("structuredEditors.currentServerCatalog")}
              document={authoritativeCatalog ?? documents.catalog}
            />
            <ReadOnlyDocument
              label={t("structuredEditors.savedCatalogSnapshot")}
              document={documents.catalog}
            />
          </DebugJsonDisclosure>
        </>
      ) : null}
      {!only && unplacedFindings.length > 0 ? (
        <section className="workspace-panel" aria-label={t("structuredEditors.unmappedAria")}>
          <p className="eyebrow">{t("structuredEditors.rawFindings")}</p>
          {unplacedFindings.map((finding) => (
            <pre className="finding-text" key={finding}>
              {findingDisplay(finding)}
            </pre>
          ))}
        </section>
      ) : null}
    </div>
  );
}
