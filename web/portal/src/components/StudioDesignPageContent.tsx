"use client";

import { useEffect, useMemo, useState } from "react";

import { JsonEditor } from "@/components/JsonEditor";
import { RegistryPublishPanel } from "@/components/RegistryPublishPanel";
import { StatusBadge } from "@/components/StatusBadge";
import { AgentFlowPanel } from "@/components/studio/AgentFlowPanel";
import { BuildVersionList } from "@/components/studio/BuildVersionList";
import { DebugJsonDisclosure } from "@/components/studio/DebugJsonDisclosure";
import {
  InterviewWorkspace,
  type EvidenceItem,
} from "@/components/studio/InterviewWorkspace";
import {
  StructuredDesignEditors,
  type DesignDocuments,
  type DesignDocumentKey,
} from "@/components/studio/StructuredDesignEditors";
import { type TranslateFn } from "@/i18n/dictionaries";
import { useTranslations } from "@/i18n/I18nProvider";
import { api, ApiError } from "@/lib/api";
import {
  isJsonDocument,
  validateDesignFormDocuments,
  type DesignFormErrors,
} from "@/lib/designForms";
import type { BuildJob, DesignStatus, HarnessDesign, ValidationFinding } from "@/lib/types";

interface StudioDesignPageContentProps {
  designId: string;
}

interface DraftDocuments {
  profile: string;
  workflow: string;
  scenarios: string;
  catalog: string;
}

type DraftDocumentField = keyof DraftDocuments;
type DraftDocumentErrors = Partial<Record<DraftDocumentField, string>>;

type StudioTabKey =
  | "evidence"
  | DesignDocumentKey
  | "agent"
  | "publish"
  | "build"
  | "debug";

const STUDIO_TABS: ReadonlyArray<{ key: StudioTabKey; labelKey: string }> = [
  { key: "evidence", labelKey: "studioDesign.tabEvidence" },
  { key: "profile", labelKey: "studioDesign.tabProfile" },
  { key: "workflow", labelKey: "studioDesign.tabWorkflow" },
  { key: "scenarios", labelKey: "studioDesign.tabScenarios" },
  { key: "agent", labelKey: "studioDesign.tabAgent" },
  { key: "catalog", labelKey: "studioDesign.tabCatalog" },
  { key: "publish", labelKey: "studioDesign.tabPublish" },
  { key: "build", labelKey: "studioDesign.tabBuild" },
  { key: "debug", labelKey: "studioDesign.tabDebug" },
];

function prettyJson(value: Record<string, unknown>): string {
  return JSON.stringify(value, null, 2);
}

function documentsFromDesign(design: HarnessDesign): DraftDocuments {
  return {
    profile: prettyJson(design.profile),
    workflow: prettyJson(design.workflow),
    scenarios: prettyJson(design.scenarios),
    catalog: prettyJson(design.catalog),
  };
}

function buildStatusFromDesign(status: DesignStatus): string | null {
  switch (status) {
    case "build-queued":
      return "queued";
    case "built":
      return "succeeded";
    case "failed":
      return "failed";
    default:
      return null;
  }
}

function canValidate(status: DesignStatus): boolean {
  return status === "draft";
}

function canReview(status: DesignStatus): boolean {
  return status === "validated";
}

function canBuild(status: DesignStatus): boolean {
  return ["approved", "failed"].includes(status);
}

function formatFinding(findings: ValidationFinding[] | null): string[] {
  return (findings ?? []).map(
    (finding) => `${finding.field}: ${finding.code}: ${finding.message}`,
  );
}

function isMappedFinding(finding: string): boolean {
  const path = finding.split(":", 1)[0]?.trim();
  return ["profile", "workflow", "scenarios", "catalog"].some(
    (prefix) => path === prefix || path.startsWith(`${prefix}.`),
  );
}

function asText(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function toFinding(value: unknown): ValidationFinding | null {
  if (!value || typeof value !== "object") {
    return null;
  }
  const candidate = value as Record<string, unknown>;
  const message = asText(candidate.message);
  if (!message) {
    return null;
  }
  return {
    field: asText(candidate.field) || "contract",
    code: asText(candidate.code) || "invalid-design",
    message,
  };
}

function findingsFromErrorPayload(payload: unknown): ValidationFinding[] | null {
  if (!payload || typeof payload !== "object") {
    return null;
  }
  const candidate = payload as Record<string, unknown>;
  const single = toFinding(candidate.finding);
  if (single) {
    return [single];
  }
  if (Array.isArray(candidate.detail)) {
    const details = candidate.detail
      .map((entry) => toFinding(entry))
      .filter((entry): entry is ValidationFinding => entry !== null);
    if (details.length > 0) {
      return details;
    }
  }
  return null;
}

function operationError(cause: unknown, fallback: string, t: TranslateFn): string {
  if (cause instanceof ApiError && cause.status === 409) {
    return t("studioDesign.conflictError", { message: cause.message });
  }
  return cause instanceof Error ? cause.message : fallback;
}

function designFromErrorPayload(payload: unknown): HarnessDesign | null {
  if (!payload || typeof payload !== "object") {
    return null;
  }
  const candidate = (payload as Record<string, unknown>).design;
  if (!candidate || typeof candidate !== "object") {
    return null;
  }
  const design = candidate as HarnessDesign;
  return typeof design.id === "string" ? design : null;
}

function parseDraftDocuments(documents: DraftDocuments): {
  profile: Record<string, unknown>;
  workflow: Record<string, unknown>;
  scenarios: Record<string, unknown>;
  catalog: Record<string, unknown>;
} {
  return {
    profile: JSON.parse(documents.profile) as Record<string, unknown>,
    workflow: JSON.parse(documents.workflow) as Record<string, unknown>,
    scenarios: JSON.parse(documents.scenarios) as Record<string, unknown>,
    catalog: JSON.parse(documents.catalog) as Record<string, unknown>,
  };
}

function fieldLabelKey(field: DraftDocumentField): string {
  const keys: Record<DraftDocumentField, string> = {
    profile: "studioDesign.profileLabel",
    workflow: "studioDesign.workflowLabel",
    scenarios: "studioDesign.scenariosLabel",
    catalog: "studioDesign.catalogLabel",
  };
  return keys[field];
}

function evidenceFromProfile(profile: Record<string, unknown>): EvidenceItem[] {
  const evidence: EvidenceItem[] = [];
  const facts = Array.isArray(profile.facts) ? profile.facts : [];
  const assumptions = Array.isArray(profile.assumptions) ? profile.assumptions : [];
  const unknowns = Array.isArray(profile.unknowns) ? profile.unknowns : [];

  facts.forEach((value, index) => {
    if (!value || typeof value !== "object") {
      return;
    }
    const fact = value as Record<string, unknown>;
    if (typeof fact.statement !== "string" || fact.statement.length === 0) {
      return;
    }
    evidence.push({
      id: typeof fact.id === "string" ? fact.id : `profile-fact-${index}`,
      statement: fact.statement,
      kind: "confirmed",
    });
  });

  assumptions.forEach((value, index) => {
    if (typeof value === "string" && value.length > 0) {
      evidence.push({
        id: `profile-assumption-${index}`,
        statement: value,
        kind: "assumption",
      });
    }
  });

  unknowns.forEach((value, index) => {
    if (typeof value === "string" && value.length > 0) {
      evidence.push({
        id: `profile-unknown-${index}`,
        statement: value,
        kind: "unknown",
      });
    }
  });

  return evidence;
}

function validateDraftDocuments(
  documents: DraftDocuments,
  t: TranslateFn,
): {
  parsed: ReturnType<typeof parseDraftDocuments> | null;
  errors: DraftDocumentErrors;
} {
  const errors: DraftDocumentErrors = {};
  const parsed = {} as ReturnType<typeof parseDraftDocuments>;

  for (const field of Object.keys(documents) as DraftDocumentField[]) {
    try {
      parsed[field] = JSON.parse(documents[field]) as Record<string, unknown>;
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : t("studioDesign.unknownSyntaxError");
      errors[field] = t("studioDesign.invalidDocument", {
        label: t(fieldLabelKey(field)),
        message,
      });
    }
  }

  return {
    parsed: Object.keys(errors).length === 0 ? parsed : null,
    errors,
  };
}

export function StudioDesignPageContent({
  designId,
}: StudioDesignPageContentProps) {
  const t = useTranslations();
  const [design, setDesign] = useState<HarnessDesign | null>(null);
  const [documents, setDocuments] = useState<DraftDocuments | null>(null);
  const [build, setBuild] = useState<BuildJob | null>(null);
  const [builds, setBuilds] = useState<BuildJob[]>([]);
  const [activeTab, setActiveTab] = useState<StudioTabKey>("profile");
  const [error, setError] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [documentErrors, setDocumentErrors] = useState<DraftDocumentErrors>({});
  const [errorFindings, setErrorFindings] = useState<ValidationFinding[] | null>(null);
  const [authoritativeCatalog, setAuthoritativeCatalog] = useState<Record<string, unknown> | null>(null);
  const [staleConflict, setStaleConflict] = useState(false);
  const [transientFormState, setTransientFormState] = useState<{
    dirty: boolean;
    errors: DesignFormErrors;
  }>({ dirty: false, errors: {} });
  const [lastValidStructuredDocuments, setLastValidStructuredDocuments] =
    useState<DesignDocuments | null>(null);

  useEffect(() => {
    let active = true;

    async function load(): Promise<void> {
      try {
        const loaded = await api<HarnessDesign>(`/designs/${designId}`);
        if (active) {
          setDesign(loaded);
          setAuthoritativeCatalog(loaded.catalog);
          setDocuments(documentsFromDesign(loaded));
          setDocumentErrors({});
          setErrorFindings(null);
          setError(null);
          setStatusMessage(t("studioDesign.savedDesign"));
        }
        if (process.env.NODE_ENV !== "test") {
          try {
            const catalog =
              await api<Record<string, unknown>>("/interviews/catalog");
            if (active) {
              setAuthoritativeCatalog(catalog);
            }
          } catch {
            // The saved snapshot remains visible; saves still use the server-owned snapshot.
          }
          try {
            const recent = await api<BuildJob[]>(`/designs/${designId}/builds`);
            if (active) {
              setBuilds(recent);
              const current =
                recent.find((item) => item.design_digest === loaded.digest) ??
                recent[0];
              if (current) {
                setBuild(current);
              }
            }
          } catch {
            // Recent build versions are best-effort; artifact download still works.
          }
        }
      } catch (cause) {
        if (active) {
          setError(cause instanceof ApiError ? cause.message : t("studioDesign.loadError"));
        }
      }
    }

    void load();

    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [designId]);

  const dirty = useMemo(() => {
    if (!design || !documents) {
      return transientFormState.dirty;
    }
    const saved = documentsFromDesign(design);
    return (
      transientFormState.dirty ||
      (Object.keys(saved) as DraftDocumentField[]).some(
        (field) => saved[field] !== documents[field],
      )
    );
  }, [design, documents, transientFormState.dirty]);

  useEffect(() => {
    function warn(event: BeforeUnloadEvent): void {
      if (dirty) {
        event.preventDefault();
      }
    }
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const findings = useMemo(
    () => formatFinding(errorFindings ?? design?.validation_findings ?? null),
    [design, errorFindings],
  );
  const mappedFindings = useMemo(
    () => findings.filter(isMappedFinding),
    [findings],
  );
  const rawFindings = useMemo(
    () => findings.filter((finding) => !isMappedFinding(finding)),
    [findings],
  );
  const profileEvidence = useMemo(
    () => (design ? evidenceFromProfile(design.profile) : []),
    [design],
  );
  const structuredDocuments = useMemo<DesignDocuments | null>(() => {
    if (!documents) {
      return null;
    }
    try {
      const profile = JSON.parse(documents.profile);
      const workflow = JSON.parse(documents.workflow);
      const scenarios = JSON.parse(documents.scenarios);
      const catalog = JSON.parse(documents.catalog);
      if (
        !isJsonDocument(profile) ||
        !isJsonDocument(workflow) ||
        !isJsonDocument(scenarios) ||
        !isJsonDocument(catalog)
      ) {
        return null;
      }
      return { profile, workflow, scenarios, catalog };
    } catch {
      return null;
    }
  }, [documents]);
  const structuredErrors = useMemo<DesignFormErrors>(
    () =>
      structuredDocuments
        ? validateDesignFormDocuments(
            structuredDocuments,
            authoritativeCatalog ?? structuredDocuments.catalog,
            t,
          )
        : {},
    [authoritativeCatalog, structuredDocuments, t],
  );
  const liveDocumentErrors = useMemo(
    () => documents ? validateDraftDocuments(documents, t).errors : {},
    [documents, t],
  );
  const visibleDocumentErrors = {
    ...documentErrors,
    ...liveDocumentErrors,
  };
  useEffect(() => {
    if (structuredDocuments) {
      setLastValidStructuredDocuments(structuredDocuments);
    }
  }, [structuredDocuments]);
  const displayedStructuredDocuments =
    structuredDocuments ?? lastValidStructuredDocuments;
  const buildStatus = build?.status ?? (design ? buildStatusFromDesign(design.status) : null);

  function updateDocument(field: keyof DraftDocuments, value: string): void {
    setDocuments((current) => (current ? { ...current, [field]: value } : current));
    setStatusMessage(t("studioDesign.unsavedChanges"));
    setDocumentErrors((current) => {
      if (!(field in current)) {
        return current;
      }
      const next = { ...current };
      delete next[field];
      return next;
    });
  }

  async function saveDraft(): Promise<void> {
    if (!design || !documents) {
      return;
    }

    setSaving(true);
    try {
      const validation = validateDraftDocuments(documents, t);
      if (!validation.parsed) {
        setDocumentErrors(validation.errors);
        setError(null);
        return;
      }
      if (
        Object.keys(structuredErrors).length > 0 ||
        Object.keys(transientFormState.errors).length > 0
      ) {
        setError(t("studioDesign.fixFormErrors"));
        return;
      }
      const updated = await api<HarnessDesign>(`/designs/${design.id}`, {
        method: "PUT",
        body: {
          expected_digest: design.digest,
          customer_id: design.customer_id,
          name: design.name,
          ...validation.parsed,
        },
      });
      setDesign(updated);
      setDocuments(documentsFromDesign(updated));
      setDocumentErrors({});
      setErrorFindings(null);
      setError(null);
      setStatusMessage(t("studioDesign.draftSaved"));
      setStaleConflict(false);
    } catch (cause) {
      setErrorFindings(
        cause instanceof ApiError ? findingsFromErrorPayload(cause.payload) : null,
      );
      setError(operationError(cause, t("studioDesign.draftSaveFailed"), t));
      setStaleConflict(cause instanceof ApiError && cause.status === 409);
    } finally {
      setSaving(false);
    }
  }

  async function reloadDesign(): Promise<void> {
    try {
      const loaded = await api<HarnessDesign>(`/designs/${designId}`);
      setDesign(loaded);
      setDocuments(documentsFromDesign(loaded));
      setStaleConflict(false);
      setError(null);
      setStatusMessage(t("studioDesign.reloadedLatest"));
    } catch (cause) {
      setError(operationError(cause, t("studioDesign.reloadFailed"), t));
    }
  }

  async function validateDesign(): Promise<void> {
    if (!design) {
      return;
    }

    setSaving(true);
    try {
      const updated = await api<HarnessDesign>(`/designs/${design.id}/validate`, {
        method: "POST",
      });
      setDesign(updated);
      setDocuments(documentsFromDesign(updated));
      setDocumentErrors({});
      setErrorFindings(null);
      setError(null);
      setStatusMessage(t("studioDesign.validatedDesign"));
    } catch (cause) {
      const payload = cause instanceof ApiError ? cause.payload : null;
      const rejected = designFromErrorPayload(payload);
      if (rejected) {
        setDesign(rejected);
        setDocuments(documentsFromDesign(rejected));
        setErrorFindings(null);
      } else {
        setErrorFindings(findingsFromErrorPayload(payload));
      }
      setDocumentErrors({});
      setError(operationError(cause, t("studioDesign.validateFailed"), t));
    } finally {
      setSaving(false);
    }
  }

  async function reviewDesign(decision: "approved" | "rejected"): Promise<void> {
    if (!design) {
      return;
    }

    setSaving(true);
    try {
      const updated = await api<HarnessDesign>(`/designs/${design.id}/reviews`, {
        method: "POST",
        body: {
          expected_digest: design.digest,
          decision,
        },
      });
      setDesign(updated);
      setDocuments(documentsFromDesign(updated));
      setDocumentErrors({});
      setErrorFindings(null);
      setError(null);
      setStatusMessage(
        decision === "approved"
          ? t("studioDesign.approvedDigest")
          : t("studioDesign.rejectedDigest"),
      );
    } catch (cause) {
      setErrorFindings(
        cause instanceof ApiError ? findingsFromErrorPayload(cause.payload) : null,
      );
      setError(operationError(cause, t("studioDesign.reviewSubmitFailed"), t));
    } finally {
      setSaving(false);
    }
  }

  async function queueBuild(): Promise<void> {
    if (!design) {
      return;
    }

    setSaving(true);
    try {
      const queued = await api<BuildJob>(`/designs/${design.id}/builds`, {
        method: "POST",
        body: {
          expected_digest: design.digest,
        },
      });
      setBuild(queued);
      setBuilds((current) => [
        queued,
        ...current.filter((item) => item.id !== queued.id),
      ]);
      setDesign((current) =>
        current ? { ...current, status: "build-queued" } : current,
      );
      setStatusMessage(t("studioDesign.buildQueued"));
      setDocumentErrors({});
      setError(null);
      try {
        const refreshed = await api<HarnessDesign>(`/designs/${design.id}`);
        setDesign(refreshed);
        setDocuments(documentsFromDesign(refreshed));
        setStatusMessage(null);
      } catch {
        setStatusMessage(t("studioDesign.buildQueuedNoRefresh"));
      }
    } catch (cause) {
      setError(operationError(cause, t("studioDesign.buildFailed"), t));
      setStatusMessage(null);
    } finally {
      setSaving(false);
    }
  }

  if (error && !design) {
    return <p className="error-text">{error}</p>;
  }

  if (!design || !documents) {
    return (
      <section className="workspace-panel state-panel" aria-busy="true">
        <p className="muted">{t("studioDesign.loading")}</p>
      </section>
    );
  }

  const renderDocumentTab = (only: DesignDocumentKey) => {
    if (!displayedStructuredDocuments) {
      return null;
    }
    return (
      <StructuredDesignEditors
        documents={displayedStructuredDocuments}
        authoritativeCatalog={authoritativeCatalog}
        findings={mappedFindings}
        errors={structuredErrors}
        only={only}
        onTransientStateChange={setTransientFormState}
        onChange={(next) => {
          setDocuments({
            profile: prettyJson(next.profile),
            workflow: prettyJson(next.workflow),
            scenarios: prettyJson(next.scenarios),
            catalog: documents.catalog,
          });
          setStatusMessage(t("studioDesign.unsavedChanges"));
        }}
      />
    );
  };

  return (
    <div className="page-stack">
      <section className="workspace-panel design-hero">
        <div className="page-header">
          <div>
            <p className="eyebrow">
              {t("studioDesign.heroEyebrow", { revision: design.revision })}
            </p>
            <h1 className="workspace-heading">{design.name}</h1>
            <p className="page-description">
              {t("studioDesign.customerId", { customer: design.customer_id })}
            </p>
          </div>
          <StatusBadge label={design.status} />
        </div>
        <div className="digest-row">
          <span>{t("studioDesign.currentDigest")}</span>
          <code className="digest-text">{design.digest}</code>
        </div>
        <div className="actions-row">
          <button
            className="button-primary"
            type="button"
            onClick={() => void saveDraft()}
            disabled={saving}
          >
            {t("studioDesign.saveDraftBtn")}
          </button>
          <button
            className="button-secondary"
            type="button"
            onClick={() => void validateDesign()}
            disabled={saving || !canValidate(design.status)}
          >
            {t("studioDesign.validateBtn")}
          </button>
          <button
            className="button-secondary"
            type="button"
            onClick={() => void reviewDesign("approved")}
            disabled={saving || !canReview(design.status)}
          >
            {t("studioDesign.approveDigestBtn")}
          </button>
          <button
            className="button-secondary"
            type="button"
            onClick={() => void reviewDesign("rejected")}
            disabled={saving || !canReview(design.status)}
          >
            {t("studioDesign.rejectReviewBtn")}
          </button>
          <button
            className="button-secondary"
            type="button"
            onClick={() => void queueBuild()}
            disabled={saving || !canBuild(design.status)}
          >
            {t("studioDesign.requestBuildBtn")}
          </button>
        </div>
        {error ? <p className="error-text">{error}</p> : null}
        {staleConflict ? (
          <div className="conflict-actions">
            <button
              className="button-secondary"
              type="button"
              onClick={() => void reloadDesign()}
            >
              {t("studioDesign.loadServerLatest")}
            </button>
            <p className="muted">{t("studioDesign.conflictNote")}</p>
          </div>
        ) : null}
        {statusMessage ? (
          <p className="save-state" role="status">
            {statusMessage}
          </p>
        ) : null}
      </section>

      <div
        className="workspace-tabs studio-tabs"
        role="tablist"
        aria-label={t("studioDesign.tabsAria")}
      >
        {STUDIO_TABS.map((tab) => (
          <button
            key={tab.key}
            type="button"
            role="tab"
            id={`studio-tab-${tab.key}`}
            aria-selected={activeTab === tab.key}
            aria-controls={`studio-panel-${tab.key}`}
            tabIndex={activeTab === tab.key ? 0 : -1}
            onClick={() => setActiveTab(tab.key)}
            onKeyDown={(event) => {
              if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") {
                return;
              }
              event.preventDefault();
              const index = STUDIO_TABS.findIndex((entry) => entry.key === activeTab);
              const delta = event.key === "ArrowRight" ? 1 : -1;
              const next =
                STUDIO_TABS[(index + delta + STUDIO_TABS.length) % STUDIO_TABS.length];
              if (next) {
                setActiveTab(next.key);
              }
            }}
          >
            {t(tab.labelKey)}
          </button>
        ))}
      </div>

      {!structuredDocuments ? (
        <section className="workspace-panel" role="alert">
          <p className="error-text">{t("studioDesign.structuredError")}</p>
        </section>
      ) : null}

      <div
        role="tabpanel"
        id="studio-panel-evidence"
        aria-labelledby="studio-tab-evidence"
        className="studio-tabpanel"
        hidden={activeTab !== "evidence"}
      >
        <InterviewWorkspace
          title={t("studioDesign.evidenceTitle", { name: design.name })}
          stage="unavailable"
          evidence={profileEvidence}
          conversation={
            <div className="unavailable-state">
              <p className="eyebrow">{t("studioDesign.interviewStatusEyebrow")}</p>
              <h3>{t("studioDesign.interviewUnavailableTitle")}</h3>
              <p>{t("studioDesign.interviewUnavailableBody")}</p>
            </div>
          }
          composer={
            <div className="composer-boundary" aria-disabled="true">
              <strong>{t("studioDesign.composerDisabledTitle")}</strong>
              <span>{t("studioDesign.composerDisabledBody")}</span>
            </div>
          }
        />
      </div>

      <div
        role="tabpanel"
        id="studio-panel-profile"
        aria-labelledby="studio-tab-profile"
        className="studio-tabpanel"
        hidden={activeTab !== "profile"}
      >
        {renderDocumentTab("profile")}
      </div>
      <div
        role="tabpanel"
        id="studio-panel-workflow"
        aria-labelledby="studio-tab-workflow"
        className="studio-tabpanel"
        hidden={activeTab !== "workflow"}
      >
        {renderDocumentTab("workflow")}
      </div>
      <div
        role="tabpanel"
        id="studio-panel-scenarios"
        aria-labelledby="studio-tab-scenarios"
        className="studio-tabpanel"
        hidden={activeTab !== "scenarios"}
      >
        {renderDocumentTab("scenarios")}
      </div>
      <div
        role="tabpanel"
        id="studio-panel-agent"
        aria-labelledby="studio-tab-agent"
        className="studio-tabpanel"
        hidden={activeTab !== "agent"}
      >
        <AgentFlowPanel
          workflow={displayedStructuredDocuments?.workflow ?? null}
          scenarios={displayedStructuredDocuments?.scenarios ?? null}
        />
      </div>
      <div
        role="tabpanel"
        id="studio-panel-catalog"
        aria-labelledby="studio-tab-catalog"
        className="studio-tabpanel"
        hidden={activeTab !== "catalog"}
      >
        {renderDocumentTab("catalog")}
      </div>

      {activeTab === "publish" ? (
        <div
          role="tabpanel"
          id="studio-panel-publish"
          aria-labelledby="studio-tab-publish"
          className="studio-tabpanel"
        >
          <RegistryPublishPanel design={design} />
        </div>
      ) : null}

      <div
        role="tabpanel"
        id="studio-panel-build"
        aria-labelledby="studio-tab-build"
        className="studio-tabpanel"
        hidden={activeTab !== "build"}
      >
        <div className="detail-grid">
          <section className="workspace-panel">
            <p className="eyebrow">{t("studioDesign.buildEyebrow")}</p>
            <h2>{t("studioDesign.buildStatusHeading")}</h2>
            <p>
              {buildStatus ? (
                <StatusBadge label={buildStatus} />
              ) : (
                t("studioDesign.noBuild")
              )}
            </p>
            {build?.artifact_digest ? (
              <p className="digest-text">{build.artifact_digest}</p>
            ) : null}
            {buildStatus === "succeeded" ? (
              <p>
                <a
                  className="download-link"
                  href={`/api/control-plane/designs/${design.id}/builds/artifact`}
                  download
                >
                  {t("studioDesign.downloadArtifact")}
                </a>
              </p>
            ) : null}
          </section>

          <BuildVersionList builds={builds} />

          <section className="workspace-panel">
            <p className="eyebrow">{t("studioDesign.serverValidationEyebrow")}</p>
            <h2>{t("studioDesign.validationResults")}</h2>
            {rawFindings.length === 0 ? (
              <p className="muted">{t("studioDesign.noFindings")}</p>
            ) : (
              <div className="finding-list">
                {rawFindings.map((finding) => (
                  <pre key={finding} className="finding-text">
                    {finding}
                  </pre>
                ))}
              </div>
            )}
          </section>
        </div>
      </div>

      <div
        role="tabpanel"
        id="studio-panel-debug"
        aria-labelledby="studio-tab-debug"
        className="studio-tabpanel"
        hidden={activeTab !== "debug"}
      >
        <DebugJsonDisclosure
          label={t("studioDesign.debugLabel")}
          hint={t("studioDesign.debugHint")}
          errors={(Object.keys(visibleDocumentErrors) as DraftDocumentField[]).flatMap(
            (field) => visibleDocumentErrors[field] ? [visibleDocumentErrors[field]] : [],
          )}
          focusTargetLabel={
            (Object.keys(visibleDocumentErrors) as DraftDocumentField[])
              .map((field) => visibleDocumentErrors[field] ? t(fieldLabelKey(field)) : null)
              .find((label): label is string => label !== null)
          }
        >
          <JsonEditor
            label="Profile"
            value={structuredDocuments?.profile ?? design.profile}
            textValue={documents.profile}
            onChange={(value) => updateDocument("profile", value)}
            errorMessage={visibleDocumentErrors.profile}
          />
          <JsonEditor
            label="Workflow"
            value={structuredDocuments?.workflow ?? design.workflow}
            textValue={documents.workflow}
            onChange={(value) => updateDocument("workflow", value)}
            errorMessage={visibleDocumentErrors.workflow}
          />
          <JsonEditor
            label="Scenarios"
            value={structuredDocuments?.scenarios ?? design.scenarios}
            textValue={documents.scenarios}
            onChange={(value) => updateDocument("scenarios", value)}
            errorMessage={visibleDocumentErrors.scenarios}
          />
          <JsonEditor
            label="Catalog"
            value={structuredDocuments?.catalog ?? design.catalog}
            textValue={documents.catalog}
            disabled
            errorMessage={visibleDocumentErrors.catalog}
          />
        </DebugJsonDisclosure>
      </div>
    </div>
  );
}
