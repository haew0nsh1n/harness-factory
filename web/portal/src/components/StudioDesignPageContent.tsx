"use client";

import { useEffect, useMemo, useState } from "react";

import { JsonEditor } from "@/components/JsonEditor";
import { RegistryPublishPanel } from "@/components/RegistryPublishPanel";
import { StatusBadge } from "@/components/StatusBadge";
import { DebugJsonDisclosure } from "@/components/studio/DebugJsonDisclosure";
import {
  InterviewWorkspace,
  type EvidenceItem,
} from "@/components/studio/InterviewWorkspace";
import {
  StructuredDesignEditors,
  type DesignDocuments,
} from "@/components/studio/StructuredDesignEditors";
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

function operationError(cause: unknown, fallback: string): string {
  if (cause instanceof ApiError && cause.status === 409) {
    return `최신 리비전과 충돌했습니다. 페이지를 새로고침한 뒤 다시 시도하세요. ${cause.message}`;
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

function fieldLabel(field: DraftDocumentField): string {
  const labels: Record<DraftDocumentField, string> = {
    profile: "프로필 JSON",
    workflow: "워크플로 JSON",
    scenarios: "시나리오 JSON",
    catalog: "카탈로그 JSON",
  };
  return labels[field];
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
      const message = cause instanceof Error ? cause.message : "알 수 없는 구문 오류";
      errors[field] = `${fieldLabel(field)}이 올바르지 않습니다: ${message}`;
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
          setStatusMessage("저장된 설계입니다.");
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
        }
      } catch (cause) {
        if (active) {
          setError(cause instanceof ApiError ? cause.message : "설계를 불러오지 못했습니다.");
        }
      }
    }

    void load();

    return () => {
      active = false;
    };
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
          )
        : {},
    [authoritativeCatalog, structuredDocuments],
  );
  const liveDocumentErrors = useMemo(
    () => documents ? validateDraftDocuments(documents).errors : {},
    [documents],
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
    setStatusMessage("저장하지 않은 변경 사항이 있습니다.");
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
      const validation = validateDraftDocuments(documents);
      if (!validation.parsed) {
        setDocumentErrors(validation.errors);
        setError(null);
        return;
      }
      if (
        Object.keys(structuredErrors).length > 0 ||
        Object.keys(transientFormState.errors).length > 0
      ) {
        setError("양식 오류를 수정한 뒤 저장하세요.");
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
      setStatusMessage("초안을 저장했습니다.");
      setStaleConflict(false);
    } catch (cause) {
      setErrorFindings(
        cause instanceof ApiError ? findingsFromErrorPayload(cause.payload) : null,
      );
      setError(operationError(cause, "초안을 저장하지 못했습니다."));
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
      setStatusMessage("서버의 최신 설계를 불러왔습니다.");
    } catch (cause) {
      setError(operationError(cause, "최신 설계를 불러오지 못했습니다."));
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
      setStatusMessage("설계 검증을 완료했습니다.");
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
      setError(operationError(cause, "설계를 검증하지 못했습니다."));
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
          ? "현재 다이제스트를 승인했습니다."
          : "현재 다이제스트를 반려했습니다.",
      );
    } catch (cause) {
      setErrorFindings(
        cause instanceof ApiError ? findingsFromErrorPayload(cause.payload) : null,
      );
      setError(operationError(cause, "검토 결과를 제출하지 못했습니다."));
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
      setStatusMessage("빌드를 요청했습니다.");
      setDocumentErrors({});
      setError(null);
      try {
        const refreshed = await api<HarnessDesign>(`/designs/${design.id}`);
        setDesign(refreshed);
        setDocuments(documentsFromDesign(refreshed));
        setStatusMessage(null);
      } catch {
        setStatusMessage("빌드를 요청했지만 최신 설계 상태를 불러오지 못했습니다.");
      }
    } catch (cause) {
      setError(operationError(cause, "빌드를 요청하지 못했습니다."));
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
        <p className="muted">설계를 불러오는 중입니다.</p>
      </section>
    );
  }

  return (
    <div className="page-stack">
      <section className="workspace-panel design-hero">
        <div className="page-header">
          <div>
            <p className="eyebrow">설계 작업공간 · 리비전 {design.revision}</p>
            <h1 className="workspace-heading">{design.name}</h1>
            <p className="page-description">고객 ID {design.customer_id}</p>
          </div>
          <StatusBadge label={design.status} />
        </div>
        <div className="digest-row">
          <span>현재 다이제스트</span>
          <code className="digest-text">{design.digest}</code>
        </div>
        <div className="actions-row">
          <button
            className="button-primary"
            type="button"
            onClick={() => void saveDraft()}
            disabled={saving}
          >
            초안 저장
          </button>
          <button
            className="button-secondary"
            type="button"
            onClick={() => void validateDesign()}
            disabled={saving || !canValidate(design.status)}
          >
            설계 검증
          </button>
          <button
            className="button-secondary"
            type="button"
            onClick={() => void reviewDesign("approved")}
            disabled={saving || !canReview(design.status)}
          >
            다이제스트 승인
          </button>
          <button
            className="button-secondary"
            type="button"
            onClick={() => void reviewDesign("rejected")}
            disabled={saving || !canReview(design.status)}
          >
            검토 반려
          </button>
          <button
            className="button-secondary"
            type="button"
            onClick={() => void queueBuild()}
            disabled={saving || !canBuild(design.status)}
          >
            빌드 요청
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
              서버 최신본 불러오기
            </button>
            <p className="muted">
              현재 로컬 편집은 그대로 유지되어 있습니다. 최신본을 불러오면 로컬
              편집을 교체합니다.
            </p>
          </div>
        ) : null}
        {statusMessage ? (
          <p className="save-state" role="status">
            {statusMessage}
          </p>
        ) : null}
      </section>

      <InterviewWorkspace
        title={`${design.name} 근거`}
        stage="unavailable"
        evidence={profileEvidence}
        conversation={
          <div className="unavailable-state">
            <p className="eyebrow">인터뷰 상태</p>
            <h3>대화형 인터뷰는 아직 제공되지 않습니다.</h3>
            <p>
              이 화면은 저장된 설계의 실제 프로필 근거만 보여 줍니다. 질문 생성과
              답변 저장은 3단계에서 서버 인터뷰 모델과 함께 연결됩니다.
            </p>
          </div>
        }
        composer={
          <div className="composer-boundary" aria-disabled="true">
            <strong>답변 입력 미제공</strong>
            <span>현재 설계는 아래 JSON 편집기에서 계속 검토하고 저장할 수 있습니다.</span>
          </div>
        }
      />

      {!structuredDocuments ? (
        <section className="workspace-panel" role="alert">
          <p className="error-text">
            구조화된 양식을 갱신할 수 없는 JSON 형식입니다. 디버그 JSON을 열어
            오류를 수정하세요. 기존 양식 상태와 원본 값은 유지되며 저장되지 않습니다.
          </p>
        </section>
      ) : null}
      {displayedStructuredDocuments ? (
        <div hidden={!structuredDocuments}>
          <StructuredDesignEditors
            documents={displayedStructuredDocuments}
            authoritativeCatalog={authoritativeCatalog}
            findings={mappedFindings}
            errors={structuredErrors}
            onTransientStateChange={setTransientFormState}
            onChange={(next) => {
              setDocuments({
                profile: prettyJson(next.profile),
                workflow: prettyJson(next.workflow),
                scenarios: prettyJson(next.scenarios),
                catalog: documents.catalog,
              });
              setStatusMessage("저장하지 않은 변경 사항이 있습니다.");
            }}
          />
        </div>
      ) : null}

      <div className="detail-grid">
      <section className="workspace-panel">
        <p className="eyebrow">빌드</p>
        <h2>빌드 상태</h2>
        <p>
          {buildStatus ? (
            <StatusBadge label={buildStatus} />
          ) : (
            "이 작업에서 요청한 빌드가 없습니다."
          )}
        </p>
        {build?.artifact_digest ? (
          <p className="digest-text">{build.artifact_digest}</p>
        ) : null}
      </section>

      <section className="workspace-panel">
        <p className="eyebrow">서버 검증</p>
        <h2>검증 결과</h2>
        {rawFindings.length === 0 ? (
          <p className="muted">검증 결과가 없습니다.</p>
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

      <RegistryPublishPanel design={design} />

      <DebugJsonDisclosure
        label="고급 / 디버그 JSON"
        hint="원문을 직접 확인하거나 구조화된 양식으로 복구할 때 사용합니다."
        errors={(Object.keys(visibleDocumentErrors) as DraftDocumentField[]).flatMap(
          (field) => visibleDocumentErrors[field] ? [visibleDocumentErrors[field]] : [],
        )}
        focusTargetLabel={
          (Object.keys(visibleDocumentErrors) as DraftDocumentField[])
            .map((field) => visibleDocumentErrors[field] ? fieldLabel(field) : null)
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
  );
}
