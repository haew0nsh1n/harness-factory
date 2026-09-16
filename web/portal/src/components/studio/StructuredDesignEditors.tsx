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
  const t = useTranslations();
  const matches = documentFindings(findings, prefix);
  if (matches.length === 0) {
    return null;
  }
  return (
    <div className="mapped-findings" aria-label={t("structuredEditors.findingAria", { prefix })}>
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
  const displayedErrors = useMemo(
    () => findingsByKnownPath(findings, errors),
    [errors, findings],
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
        {findings.length > 0 ? (
          <section className="workspace-panel" aria-label={t("structuredEditors.rawFindings")}>
            <p className="eyebrow">{t("structuredEditors.rawFindings")}</p>
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
      {unplacedFindings.length > 0 ? (
        <section className="workspace-panel" aria-label={t("structuredEditors.unmappedAria")}>
          <p className="eyebrow">{t("structuredEditors.rawFindings")}</p>
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
