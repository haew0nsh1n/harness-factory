"use client";

import { useEffect, useMemo, useState } from "react";

import { JsonEditor } from "@/components/JsonEditor";
import { StatusBadge } from "@/components/StatusBadge";
import { api, ApiError } from "@/lib/api";
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
  return ["approved", "built", "failed"].includes(status);
}

function formatFinding(findings: ValidationFinding[] | null): string[] {
  return (findings ?? []).map(
    (finding) => `${finding.field}: ${finding.code}: ${finding.message}`,
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

function fieldLabel(field: DraftDocumentField): string {
  return `${field.charAt(0).toUpperCase()}${field.slice(1)} JSON`;
}

function validateDraftDocuments(documents: DraftDocuments): {
  parsed: ReturnType<typeof parseDraftDocuments> | null;
  errors: DraftDocumentErrors;
} {
  const errors: DraftDocumentErrors = {};
  const parsed = {} as ReturnType<typeof parseDraftDocuments>;

  for (const field of Object.keys(documents) as DraftDocumentField[]) {
    try {
      parsed[field] = JSON.parse(documents[field]) as Record<string, unknown>;
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : "Unknown parse error";
      errors[field] = `${fieldLabel(field)} is invalid: ${message}`;
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
  const [design, setDesign] = useState<HarnessDesign | null>(null);
  const [documents, setDocuments] = useState<DraftDocuments | null>(null);
  const [build, setBuild] = useState<BuildJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [documentErrors, setDocumentErrors] = useState<DraftDocumentErrors>({});
  const [errorFindings, setErrorFindings] = useState<ValidationFinding[] | null>(null);

  useEffect(() => {
    let active = true;

    async function load(): Promise<void> {
      try {
        const loaded = await api<HarnessDesign>(`/designs/${designId}`);
        if (active) {
          setDesign(loaded);
          setDocuments(documentsFromDesign(loaded));
          setDocumentErrors({});
          setErrorFindings(null);
          setError(null);
          setStatusMessage(null);
        }
      } catch (cause) {
        if (active) {
          setError(cause instanceof ApiError ? cause.message : "Unable to load design.");
        }
      }
    }

    void load();

    return () => {
      active = false;
    };
  }, [designId]);

  const findings = useMemo(
    () => formatFinding(errorFindings ?? design?.validation_findings ?? null),
    [design, errorFindings],
  );
  const buildStatus = build?.status ?? (design ? buildStatusFromDesign(design.status) : null);

  function updateDocument(field: keyof DraftDocuments, value: string): void {
    setDocuments((current) => (current ? { ...current, [field]: value } : current));
    setDocumentErrors((current) => {
      if (!current[field]) {
        return current;
      }
      return { ...current, [field]: undefined };
    });
  }

  async function saveDraft(): Promise<void> {
    if (!design || !documents) {
      return;
    }

    setSaving(true);
    try {
      const validation = validateDraftDocuments(documents);
      if (!validation.parsed) {
        setDocumentErrors(validation.errors);
        setError(null);
        return;
      }
      const updated = await api<HarnessDesign>(`/designs/${design.id}`, {
        method: "PUT",
        body: {
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
    } catch (cause) {
      setErrorFindings(
        cause instanceof ApiError ? findingsFromErrorPayload(cause.payload) : null,
      );
      setError(cause instanceof Error ? cause.message : "Unable to save draft.");
    } finally {
      setSaving(false);
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
      setError(cause instanceof Error ? cause.message : "Unable to validate design.");
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
    } catch (cause) {
      setErrorFindings(
        cause instanceof ApiError ? findingsFromErrorPayload(cause.payload) : null,
      );
      setError(cause instanceof Error ? cause.message : "Unable to submit review.");
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
      setDesign((current) =>
        current ? { ...current, status: "build-queued" } : current,
      );
      setStatusMessage("Build queued.");
      setDocumentErrors({});
      setError(null);
      try {
        const refreshed = await api<HarnessDesign>(`/designs/${design.id}`);
        setDesign(refreshed);
        setDocuments(documentsFromDesign(refreshed));
        setStatusMessage(null);
      } catch {
        setStatusMessage("Build queued. Unable to refresh latest design status.");
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to queue build.");
      setStatusMessage(null);
    } finally {
      setSaving(false);
    }
  }

  if (error && !design) {
    return <p className="error-text">{error}</p>;
  }

  if (!design || !documents) {
    return <p className="muted">Loading design…</p>;
  }

  return (
    <div className="detail-grid">
      <section className="card">
        <div className="page-header">
          <div>
            <h1>{design.name}</h1>
            <p className="muted">{design.customer_id}</p>
          </div>
          <StatusBadge label={design.status} />
        </div>
        <p className="digest-text">{design.digest}</p>
        <div className="actions-row">
          <button type="button" onClick={() => void saveDraft()} disabled={saving}>
            Save draft
          </button>
          <button
            type="button"
            onClick={() => void validateDesign()}
            disabled={saving || !canValidate(design.status)}
          >
            Validate
          </button>
          <button
            type="button"
            onClick={() => void reviewDesign("approved")}
            disabled={saving || !canReview(design.status)}
          >
            Approve digest
          </button>
          <button
            type="button"
            onClick={() => void reviewDesign("rejected")}
            disabled={saving || !canReview(design.status)}
          >
            Reject digest
          </button>
          <button
            type="button"
            onClick={() => void queueBuild()}
            disabled={saving || !canBuild(design.status)}
          >
            Queue build
          </button>
        </div>
        {error ? <p className="error-text">{error}</p> : null}
        {statusMessage ? <p className="muted">{statusMessage}</p> : null}
      </section>

      <section className="card">
        <h2>Build status</h2>
        <p>
          {buildStatus ? <StatusBadge label={buildStatus} /> : "No build submitted for this session."}
        </p>
        {build?.artifact_digest ? (
          <p className="digest-text">{build.artifact_digest}</p>
        ) : null}
      </section>

      <section className="card">
        <h2>Server findings</h2>
        {findings.length === 0 ? (
          <p className="muted">No validation findings.</p>
        ) : (
          <div className="finding-list">
            {findings.map((finding) => (
              <pre key={finding} className="finding-text">
                {finding}
              </pre>
            ))}
          </div>
        )}
      </section>

      <JsonEditor
        label="Profile"
        value={design.profile}
        onChange={(value) => updateDocument("profile", value)}
        errorMessage={documentErrors.profile}
      />
      <JsonEditor
        label="Workflow"
        value={design.workflow}
        onChange={(value) => updateDocument("workflow", value)}
        errorMessage={documentErrors.workflow}
      />
      <JsonEditor
        label="Scenarios"
        value={design.scenarios}
        onChange={(value) => updateDocument("scenarios", value)}
        errorMessage={documentErrors.scenarios}
      />
      <JsonEditor
        label="Catalog"
        value={design.catalog}
        onChange={(value) => updateDocument("catalog", value)}
        errorMessage={documentErrors.catalog}
      />
    </div>
  );
}
