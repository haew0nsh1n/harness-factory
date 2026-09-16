"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import {
  InterviewWorkspace,
  type EvidenceItem,
} from "@/components/studio/InterviewWorkspace";
import {
  StructuredDesignEditors,
  type DesignDocuments,
} from "@/components/studio/StructuredDesignEditors";
import {
  clearAnswerOperation,
  clearInterviewOperations,
  clearProposalOperation,
  clearStartOperation,
  readAnswerOperation,
  readProposalOperation,
  readSelectedProposal,
  readStartOperation,
  writeAnswerOperation,
  writeProposalOperation,
  writeSelectedProposal,
  writeStartOperation,
  type AnswerOperationEnvelope,
  type ProposalOperationEnvelope,
  type StartOperationEnvelope,
} from "@/components/studio/interviewOperations";
import { api, ApiError } from "@/lib/api";
import type {
  HarnessDesign,
  InterviewProposal,
  InterviewProposalSummary,
  InterviewSession,
} from "@/lib/types";

interface InterviewPageContentProps {
  interviewId?: string;
  navigate?: (path: string) => void;
}

const CONSENT_VERSION = "2026-09-15" as const;
const NEW_DESIGN = "new";

function requestId(): string {
  if (typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function composerKey(interviewId: string): string {
  return `hf-interview-composer:${interviewId}`;
}

function safeError(cause: unknown): string {
  if (!(cause instanceof ApiError)) {
    return "요청을 완료하지 못했습니다. 네트워크 연결을 확인하고 다시 시도하세요.";
  }
  const messages: Record<string, string> = {
    llm_not_configured:
      "인터뷰 모델이 구성되지 않았습니다. 기존 설계 편집은 계속 사용할 수 있습니다.",
    llm_auth_unavailable:
      "Azure OpenAI 인증을 사용할 수 없습니다. 관리자에게 모델 ID 권한을 확인해 달라고 요청하세요.",
    llm_throttled:
      "Azure OpenAI가 현재 요청을 제한하고 있습니다. 잠시 후 같은 요청을 다시 시도하세요.",
    llm_timeout:
      "모델 응답이 시간 안에 완료되지 않았습니다. 저장된 동일 요청을 다시 시도할 수 있습니다.",
    llm_refused:
      "모델이 이 요청에 답하지 않았습니다. 비밀, 코드, 이슈 본문을 제거하고 새 요청으로 보내세요.",
    llm_invalid_result:
      "모델 응답이 인터뷰 형식 검사를 통과하지 못했습니다. 저장된 동일 요청을 다시 시도하세요.",
    llm_context_limit:
      "인터뷰 문맥 한도에 도달했습니다. 현재 근거로 제안을 검토하거나 인터뷰를 삭제하세요.",
    turn_limit:
      "인터뷰 질문 한도에 도달했습니다. 현재 근거로 제안을 검토하거나 인터뷰를 삭제하세요.",
    interview_busy:
      "다른 인터뷰 작업이 진행 중입니다. 완료된 상태를 다시 불러온 뒤 시도하세요.",
    operation_superseded:
      "이 요청보다 최신 작업이 저장되었습니다. 현재 인터뷰를 다시 불러오세요.",
    request_id_reused:
      "이 요청 ID가 다른 내용에 사용되었습니다. 입력을 확인하고 새 요청으로 보내세요.",
    stale_revision:
      "다른 변경이 먼저 저장되었습니다. 작성 중인 답변은 유지했습니다. 최신 상태를 다시 불러오세요.",
    stale_proposal:
      "검토한 제안과 서버 제안의 다이제스트가 다릅니다. 저장된 제안을 다시 불러와 검토하세요.",
    stale_digest:
      "대상 설계가 검토 후 변경되었습니다. 제안은 유지되며 대상 설계를 다시 불러와 재검토해야 합니다.",
    scope_not_selected:
      "워크플로 범위가 아직 선택되지 않았습니다. 인터뷰를 계속해 범위를 확정하세요.",
    scope_mismatch:
      "제안된 워크플로 ID가 선택한 범위와 일치하지 않습니다. 제안을 다시 생성하세요.",
    proposal_already_applied:
      "이 제안은 이미 설계에 적용되었습니다. 저장된 설계를 확인하세요.",
    target_design_not_found:
      "적용 대상 설계를 찾을 수 없습니다. 제안과 작성 중인 답변은 유지했습니다. 적용 대상을 다시 선택하고 검토하세요.",
    secret_detected:
      "비밀로 보이는 값이 감지되어 저장하거나 전송하지 않았습니다. 자격 증명과 토큰을 제거하세요.",
  };
  return (
    messages[cause.code] ??
    "인터뷰 요청을 완료하지 못했습니다. 현재 상태를 다시 불러온 뒤 시도하세요."
  );
}

function evidenceItems(session: InterviewSession): EvidenceItem[] {
  return [
    ...session.confirmed_evidence.map((item) => ({
      id: item.id,
      statement: item.statement,
      sourceTurnIds: item.source_turn_ids,
      kind: item.kind === "fact" ? ("confirmed" as const) : item.kind,
    })),
    ...session.proposed_evidence.map((item) => ({
      id: item.id,
      statement: item.statement,
      sourceTurnIds: item.source_turn_ids,
      kind: "proposed" as const,
    })),
  ];
}

function proposalDocuments(proposal: InterviewProposal): DesignDocuments {
  return {
    profile: proposal.profile,
    workflow: proposal.workflow,
    scenarios: proposal.scenarios,
    catalog: proposal.catalog,
  };
}

function formatDate(value: string): string {
  return new Date(value).toLocaleString("ko-KR");
}

function preferredProposal(
  summaries: InterviewProposalSummary[],
  selectedId: string | null,
): InterviewProposalSummary | null {
  const selected = summaries.find((item) => item.id === selectedId);
  if (selected) {
    return selected;
  }
  return (
    [...summaries].reverse().find((item) => item.status === "draft") ??
    summaries.at(-1) ??
    null
  );
}

function proposalMatchesSummary(
  proposal: InterviewProposal,
  summary: InterviewProposalSummary,
): boolean {
  return (
    proposal.id === summary.id &&
    proposal.revision === summary.revision &&
    proposal.digest === summary.digest
  );
}

export function InterviewPageContent({
  interviewId,
  navigate = (path) => window.location.assign(path),
}: InterviewPageContentProps) {
  const [session, setSession] = useState<InterviewSession | null>(null);
  const [designs, setDesigns] = useState<HarnessDesign[]>([]);
  const [name, setName] = useState("");
  const [customerId, setCustomerId] = useState("");
  const [consented, setConsented] = useState(false);
  const [answer, setAnswer] = useState("");
  const [startOperation, setStartOperation] =
    useState<StartOperationEnvelope | null>(null);
  const [answerOperation, setAnswerOperation] =
    useState<AnswerOperationEnvelope | null>(null);
  const [proposalOperation, setProposalOperation] =
    useState<ProposalOperationEnvelope | null>(null);
  const [proposal, setProposal] = useState<InterviewProposal | null>(null);
  const [proposalDraft, setProposalDraft] = useState<DesignDocuments | null>(
    null,
  );
  const [targetDesignId, setTargetDesignId] = useState(NEW_DESIGN);
  const [targetStale, setTargetStale] = useState(false);
  const [confirmedReviewIdentity, setConfirmedReviewIdentity] = useState<
    string | null
  >(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deleteArmed, setDeleteArmed] = useState(false);
  const alive = useRef(true);
  const terminal = useRef(false);

  const targetDesign =
    targetDesignId === NEW_DESIGN
      ? null
      : designs.find((item) => item.id === targetDesignId) ?? null;
  const reviewIdentity =
    session && proposal
      ? JSON.stringify({
          proposal_id: proposal.id,
          proposal_digest: proposal.digest,
          scope: session.scope,
          design_id: targetDesign?.id ?? null,
          design_digest: targetDesign?.digest ?? null,
        })
      : null;
  const scopeConfirmed =
    reviewIdentity !== null && confirmedReviewIdentity === reviewIdentity;

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  useEffect(() => {
    if (!interviewId) {
      const stored = readStartOperation();
      setStartOperation(stored);
      if (stored) {
        setName(stored.name);
        setCustomerId(stored.customer_id);
        setConsented(true);
      }
      return;
    }
    terminal.current = false;
    setAnswer(window.sessionStorage.getItem(composerKey(interviewId)) ?? "");
    setAnswerOperation(readAnswerOperation(interviewId));
    setProposalOperation(readProposalOperation(interviewId));
    void loadSession();
    void loadDesigns();
  }, [interviewId]);

  useEffect(() => {
    if (!interviewId || terminal.current) {
      return;
    }
    window.sessionStorage.setItem(composerKey(interviewId), answer);
  }, [answer, interviewId]);

  useEffect(() => {
    setConfirmedReviewIdentity(null);
    setTargetStale(false);
  }, [
    proposal?.id,
    proposal?.digest,
    session?.scope,
    targetDesign?.id,
    targetDesign?.digest,
  ]);

  useEffect(() => {
    function warn(event: BeforeUnloadEvent): void {
      if (answer.trim()) {
        event.preventDefault();
      }
    }
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [answer]);

  function clearSessionSensitiveState(id: string): void {
    terminal.current = true;
    window.sessionStorage.removeItem(composerKey(id));
    clearInterviewOperations(id);
    setSession(null);
    setAnswer("");
    setAnswerOperation(null);
    setProposalOperation(null);
    setProposal(null);
    setProposalDraft(null);
    setConfirmedReviewIdentity(null);
    setDeleteArmed(false);
  }

  function handleTerminalNotFound(id: string): void {
    clearSessionSensitiveState(id);
    setError(
      "인터뷰가 만료되었거나 삭제되었습니다. 30일 보존 기간이 지난 인터뷰는 다시 열 수 없습니다.",
    );
  }

  function handleSessionFailure(cause: unknown, id: string): boolean {
    if (cause instanceof ApiError && cause.status === 404) {
      handleTerminalNotFound(id);
      return true;
    }
    return false;
  }

  function reconcileAnswerOperation(
    loaded: InterviewSession,
    stored: AnswerOperationEnvelope | null,
  ): void {
    if (
      !stored ||
      loaded.last_operation?.request_id !== stored.request_id ||
      loaded.last_operation.status !== "succeeded"
    ) {
      return;
    }
    clearAnswerOperation(loaded.id);
    setAnswerOperation(null);
    setAnswer((current) => {
      if (current.trim() === stored.answer) {
        window.sessionStorage.removeItem(composerKey(loaded.id));
        return "";
      }
      return current;
    });
  }

  async function loadProposal(
    loaded: InterviewSession,
    summary: InterviewProposalSummary,
  ): Promise<void> {
    try {
      const detail = await api<InterviewProposal>(
        `/interviews/${loaded.id}/proposals/${summary.id}`,
      );
      if (!proposalMatchesSummary(detail, summary)) {
        setProposal(null);
        setProposalDraft(null);
        setError(
          "저장된 제안 요약과 본문의 다이제스트가 다릅니다. 적용하지 말고 관리자에게 확인하세요.",
        );
        return;
      }
      if (alive.current) {
        setProposal(detail);
        setProposalDraft(proposalDocuments(detail));
        writeSelectedProposal(loaded.id, detail.id);
      }
    } catch (cause) {
      if (!alive.current) {
        return;
      }
      if (cause instanceof ApiError && cause.status === 404) {
        handleTerminalNotFound(loaded.id);
      } else {
        setError(safeError(cause));
      }
    }
  }

  async function loadSession(): Promise<void> {
    if (!interviewId) {
      return;
    }
    try {
      const loaded = await api<InterviewSession>(`/interviews/${interviewId}`);
      if (!alive.current) {
        return;
      }
      setSession(loaded);
      setError(null);
      const storedAnswer = readAnswerOperation(interviewId);
      setAnswerOperation(storedAnswer);
      reconcileAnswerOperation(loaded, storedAnswer);

      const storedProposalOperation = readProposalOperation(interviewId);
      if (
        storedProposalOperation &&
        loaded.last_operation?.request_id ===
          storedProposalOperation.request_id &&
        loaded.last_operation.status === "succeeded"
      ) {
        clearProposalOperation(interviewId);
        setProposalOperation(null);
      } else {
        setProposalOperation(storedProposalOperation);
      }

      const selected = preferredProposal(
        loaded.proposals,
        readSelectedProposal(interviewId),
      );
      if (selected) {
        await loadProposal(loaded, selected);
      } else {
        setProposal(null);
        setProposalDraft(null);
      }
    } catch (cause) {
      if (!alive.current) {
        return;
      }
      if (cause instanceof ApiError && cause.status === 404) {
        handleTerminalNotFound(interviewId);
      } else {
        setError(safeError(cause));
      }
    }
  }

  async function loadDesigns(): Promise<void> {
    try {
      const loaded = await api<HarnessDesign[]>("/designs");
      if (alive.current) {
        setDesigns(loaded);
      }
    } catch (cause) {
      if (alive.current) {
        setError(safeError(cause));
      }
    }
  }

  async function startInterview(): Promise<void> {
    if (!consented || busy) {
      return;
    }
    const normalizedName = name.trim();
    const normalizedCustomerId = customerId.trim();
    if (!normalizedName || !normalizedCustomerId) {
      setError("인터뷰 이름과 고객 ID를 입력하세요.");
      return;
    }
    const existing = startOperation ?? readStartOperation();
    const operation =
      existing &&
      existing.name === normalizedName &&
      existing.customer_id === normalizedCustomerId
        ? existing
        : {
            name: normalizedName,
            customer_id: normalizedCustomerId,
            consent_version: CONSENT_VERSION,
            consent_accepted: true as const,
            request_id: requestId(),
          };
    setStartOperation(operation);
    writeStartOperation(operation);
    setBusy(true);
    setError(null);
    try {
      const created = await api<InterviewSession>("/interviews", {
        method: "POST",
        body: operation,
      });
      clearStartOperation();
      setStartOperation(null);
      navigate(`/studio/interviews/${created.id}`);
    } catch (cause) {
      setError(safeError(cause));
    } finally {
      setBusy(false);
    }
  }

  async function sendAnswer(retry = false): Promise<void> {
    if (!session || busy) {
      return;
    }
    const operation = retry
      ? answerOperation
      : {
          expected_revision: session.revision,
          request_id: requestId(),
          answer: answer.trim(),
        };
    if (!operation?.answer) {
      return;
    }
    setAnswerOperation(operation);
    writeAnswerOperation(session.id, operation);
    setBusy(true);
    setError(null);
    try {
      const updated = await api<InterviewSession>(
        `/interviews/${session.id}/turns`,
        {
          method: "POST",
          body: operation,
        },
      );
      setSession(updated);
      clearAnswerOperation(session.id);
      setAnswerOperation(null);
      setAnswer((current) => {
        if (current.trim() === operation.answer) {
          window.sessionStorage.removeItem(composerKey(session.id));
          return "";
        }
        return current;
      });
    } catch (cause) {
      if (!handleSessionFailure(cause, session.id)) {
        setError(safeError(cause));
      }
    } finally {
      setBusy(false);
    }
  }

  async function decideEvidence(
    evidenceId: string,
    decision: "confirm" | "reject",
  ): Promise<void> {
    if (!session || busy) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const updated = await api<InterviewSession>(
        `/interviews/${session.id}/confirmations`,
        {
          method: "POST",
          body: {
            expected_revision: session.revision,
            request_id: requestId(),
            decisions: [{ evidence_id: evidenceId, decision }],
          },
        },
      );
      setSession(updated);
    } catch (cause) {
      if (!handleSessionFailure(cause, session.id)) {
        setError(safeError(cause));
      }
    } finally {
      setBusy(false);
    }
  }

  async function generateProposal(): Promise<void> {
    if (!session || busy) {
      return;
    }
    const existing = proposalOperation ?? readProposalOperation(session.id);
    const operation =
      existing && existing.expected_revision === session.revision
        ? existing
        : {
            expected_revision: session.revision,
            request_id: requestId(),
          };
    setProposalOperation(operation);
    writeProposalOperation(session.id, operation);
    setBusy(true);
    setError(null);
    try {
      const generated = await api<InterviewProposal>(
        `/interviews/${session.id}/proposals`,
        {
          method: "POST",
          body: operation,
        },
      );
      setProposal(generated);
      setProposalDraft(proposalDocuments(generated));
      writeSelectedProposal(session.id, generated.id);
      clearProposalOperation(session.id);
      setProposalOperation(null);
      await loadSession();
    } catch (cause) {
      if (!handleSessionFailure(cause, session.id)) {
        setError(safeError(cause));
      }
    } finally {
      setBusy(false);
    }
  }

  async function selectProposal(proposalId: string): Promise<void> {
    if (!session || busy) {
      return;
    }
    const summary = session.proposals.find((item) => item.id === proposalId);
    if (!summary) {
      return;
    }
    setBusy(true);
    setError(null);
    writeSelectedProposal(session.id, proposalId);
    await loadProposal(session, summary);
    setBusy(false);
  }

  async function applyProposal(): Promise<void> {
    if (
      !session ||
      !proposal ||
      !proposalDraft ||
      !scopeConfirmed ||
      busy
    ) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const design = await api<HarnessDesign>(`/interviews/${session.id}/apply`, {
        method: "POST",
        body: {
          expected_revision: proposal.revision,
          proposal_id: proposal.id,
          expected_proposal_digest: proposal.digest,
          confirm_scope: true,
          design_id: targetDesign?.id ?? null,
          expected_design_digest: targetDesign?.digest ?? null,
        },
      });
      navigate(`/studio/${design.id}`);
    } catch (cause) {
      if (
        cause instanceof ApiError &&
        cause.code === "target_design_not_found"
      ) {
        const missingTargetId = targetDesign?.id;
        if (missingTargetId) {
          setDesigns((current) =>
            current.filter((item) => item.id !== missingTargetId),
          );
        }
        setTargetDesignId(NEW_DESIGN);
        setConfirmedReviewIdentity(null);
        setTargetStale(false);
        setError(safeError(cause));
        return;
      }
      if (handleSessionFailure(cause, session.id)) {
        return;
      }
      if (cause instanceof ApiError && cause.code === "stale_digest") {
        setConfirmedReviewIdentity(null);
        setTargetStale(true);
      }
      setError(safeError(cause));
    } finally {
      setBusy(false);
    }
  }

  async function reloadTargetDesign(): Promise<void> {
    if (!targetDesign || busy) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const loaded = await api<HarnessDesign>(`/designs/${targetDesign.id}`);
      setDesigns((current) =>
        current.map((item) => (item.id === loaded.id ? loaded : item)),
      );
      setTargetStale(false);
      setConfirmedReviewIdentity(null);
    } catch (cause) {
      setError(safeError(cause));
    } finally {
      setBusy(false);
    }
  }

  async function deleteInterview(): Promise<void> {
    if (!session || busy) {
      return;
    }
    setBusy(true);
    try {
      await api(`/interviews/${session.id}`, { method: "DELETE" });
      clearSessionSensitiveState(session.id);
      navigate("/studio");
    } catch (cause) {
      if (!handleSessionFailure(cause, session.id)) {
        setError(safeError(cause));
      }
    } finally {
      setBusy(false);
    }
  }

  const evidence = useMemo(
    () => (session ? evidenceItems(session) : []),
    [session],
  );

  if (!interviewId) {
    return (
      <div className="page-stack">
        <header className="page-intro">
          <p className="eyebrow">새 AI 인터뷰</p>
          <h1 className="workspace-heading">SDLC 인터뷰 시작</h1>
          <p className="page-description">
            첫 질문을 요청하기 전에 전송 대상과 보존 경계를 확인합니다.
          </p>
        </header>
        <section className="workspace-panel consent-panel" aria-busy={busy}>
          <div className="form-grid">
            <label className="field">
              <span>인터뷰 이름</span>
              <input
                value={name}
                disabled={busy}
                onChange={(event) => setName(event.target.value)}
              />
            </label>
            <label className="field">
              <span>고객 ID</span>
              <input
                value={customerId}
                disabled={busy}
                onChange={(event) => setCustomerId(event.target.value)}
                pattern="[a-z0-9][a-z0-9-]*"
              />
            </label>
          </div>
          <div className="privacy-notice">
            <h2>전송 및 보존 확인</h2>
            <p>
              작성한 인터뷰 텍스트는 구성된 Azure OpenAI 배포로 전송되며
              Responses 요청은 store: false로 처리됩니다. 인터뷰와 확인한 근거는
              조직 범위 데이터베이스에 마지막 활동부터 30일간 보존됩니다.
            </p>
            <p>
              인터뷰 삭제는 대화와 미적용 제안을 제거하지만 이미 만든 설계는
              삭제하지 않습니다. 비밀, 자격 증명, 소스 코드, 저장소 파일 또는
              이슈 본문을 입력하지 마세요. 패턴 검사는 모든 민감 정보를 보장해
              찾을 수 없습니다.
            </p>
            <label className="consent-check">
              <input
                type="checkbox"
                checked={consented}
                disabled={busy}
                onChange={(event) => setConsented(event.target.checked)}
              />
              <span>
                Azure OpenAI 전송과 30일 보존·삭제 동작을 이해하고 인터뷰 시작에
                동의합니다.
              </span>
            </label>
          </div>
          <button
            className="button-primary"
            type="button"
            disabled={!consented || busy}
            onClick={() => void startInterview()}
          >
            인터뷰 시작
          </button>
          {error ? (
            <p className="error-text" role="alert">
              {error}
            </p>
          ) : null}
        </section>
      </div>
    );
  }

  if (!session) {
    return (
      <section className="workspace-panel state-panel" aria-busy={!error}>
        <p className={error ? "error-text" : "muted"}>
          {error ?? "인터뷰를 불러오는 중입니다."}
        </p>
        {error ? (
          <a className="button-secondary" href="/studio/interviews/new">
            새 인터뷰 시작
          </a>
        ) : null}
      </section>
    );
  }

  return (
    <div className="page-stack" aria-busy={busy}>
      <section className="workspace-panel interview-session-header">
        <div className="page-header">
          <div>
            <p className="eyebrow">AI 인터뷰 · 리비전 {session.revision}</p>
            <h1 className="workspace-heading">{session.name}</h1>
            <p className="page-description">
              고객 ID {session.customer_id} · {formatDate(session.updated_at)} 저장 ·{" "}
              {formatDate(session.expires_at)} 만료
            </p>
          </div>
          <a className="button-secondary" href="/studio">
            스튜디오로
          </a>
        </div>
        {error ? (
          <div className="conflict-banner" role="alert">
            <p>{error}</p>
            <button
              className="button-secondary button-compact"
              type="button"
              disabled={busy}
              onClick={() => void loadSession()}
            >
              최신 상태 다시 불러오기
            </button>
          </div>
        ) : null}
      </section>

      <InterviewWorkspace
        title={session.name}
        stage={session.stage}
        evidence={evidence}
        onConfirm={(id) => void decideEvidence(id, "confirm")}
        boundary="질문, 답변, 근거 출처는 서버에 저장된 실제 인터뷰 기록입니다."
        conversation={
          <div className="turn-list" aria-live="polite">
            {session.turns.map((turn) => (
              <article
                className={`interview-turn turn-${turn.role}`}
                id={`turn-${turn.id}`}
                key={turn.id}
              >
                <p className="turn-role">
                  {turn.role === "assistant" ? "질문" : "답변"}
                </p>
                <p>{turn.text}</p>
              </article>
            ))}
          </div>
        }
        composer={
          <div className="answer-composer">
            <label className="field">
              <span>답변</span>
              <textarea
                aria-label="답변"
                rows={5}
                maxLength={8000}
                value={answer}
                disabled={busy}
                onChange={(event) => setAnswer(event.target.value)}
                placeholder="확인 가능한 사실과 아직 모르는 내용을 구분해 입력하세요."
              />
            </label>
            <div className="composer-actions">
              <span>
                {answer.length}/8000 · 입력 중에는 모델을 호출하지 않습니다.
              </span>
              <button
                className="button-primary"
                type="button"
                disabled={!answer.trim() || busy}
                onClick={() => void sendAnswer(false)}
              >
                답변 보내기
              </button>
              {answerOperation ? (
                <button
                  className="button-secondary"
                  type="button"
                  disabled={busy}
                  onClick={() => void sendAnswer(true)}
                >
                  저장된 요청 다시 시도
                </button>
              ) : null}
            </div>
          </div>
        }
      />

      {session.proposed_evidence.length > 0 ? (
        <section className="workspace-panel">
          <p className="eyebrow">사람의 확인 필요</p>
          <h2>제안된 근거 결정</h2>
          {session.proposed_evidence.map((item) => (
            <div className="review-row" key={item.id}>
              <p>{item.statement}</p>
              <div className="actions-row">
                <button
                  className="button-secondary"
                  type="button"
                  disabled={busy}
                  onClick={() => void decideEvidence(item.id, "confirm")}
                >
                  사실 확인
                </button>
                <button
                  className="button-secondary"
                  type="button"
                  disabled={busy}
                  onClick={() => void decideEvidence(item.id, "reject")}
                >
                  근거 거절
                </button>
              </div>
            </div>
          ))}
        </section>
      ) : null}

      <section className="workspace-panel proposal-action">
        <div>
          <p className="eyebrow">명시적 제안 생성</p>
          <h2>현재 확인 근거로 설계 제안 만들기</h2>
          <p className="muted">
            이 버튼을 누를 때만 모델이 프로필, 워크플로, 시나리오 초안을 생성합니다.
          </p>
        </div>
        <button
          className="button-primary"
          type="button"
          disabled={busy}
          onClick={() => void generateProposal()}
        >
          {proposalOperation ? "저장된 제안 요청 다시 시도" : "설계 제안 생성"}
        </button>
      </section>

      {session.proposals.length > 0 ? (
        <section className="workspace-panel">
          <label className="field">
            <span>검토할 저장된 제안</span>
            <select
              aria-label="검토할 저장된 제안"
              value={proposal?.id ?? ""}
              disabled={busy}
              onChange={(event) => void selectProposal(event.target.value)}
            >
              {session.proposals.map((item) => (
                <option value={item.id} key={item.id}>
                  리비전 {item.revision} · {item.status} · {item.digest.slice(0, 12)}
                </option>
              ))}
            </select>
          </label>
        </section>
      ) : null}

      {proposal && proposalDraft ? (
        <>
          <section className="workspace-panel proposal-review-header">
            <p className="eyebrow">정확한 제안 검토</p>
            <h2>제안 다이제스트</h2>
            <code className="digest-text">{proposal.digest}</code>
            <p>
              아래 문서는 읽기 전용입니다. 적용 요청은 서버에 저장된 이 정확한
              다이제스트를 사용하며, 설계 승인과는 별개입니다.
            </p>
          </section>
          <StructuredDesignEditors
            documents={proposalDraft}
            authoritativeCatalog={proposal.catalog}
            onChange={setProposalDraft}
            readOnly
            findings={proposal.findings.map((finding) =>
              Object.entries(finding)
                .map(([key, value]) => `${key}: ${value}`)
                .join(" · "),
            )}
          />
          <section className="workspace-panel apply-panel">
            <label className="field">
              <span>적용 대상</span>
              <select
                aria-label="적용 대상"
                value={targetDesignId}
                disabled={busy}
                onChange={(event) => {
                  setTargetDesignId(event.target.value);
                  setTargetStale(false);
                }}
              >
                <option value={NEW_DESIGN}>새 설계 만들기</option>
                {designs.map((design) => (
                  <option value={design.id} key={design.id}>
                    기존 설계 · {design.name}
                  </option>
                ))}
              </select>
            </label>
            <p className="muted">
              대상 현재 다이제스트:{" "}
              <code>{targetDesign?.digest ?? "새 설계에는 기존 다이제스트 없음"}</code>
            </p>
            {targetStale && targetDesign ? (
              <button
                className="button-secondary"
                type="button"
                disabled={busy}
                onClick={() => void reloadTargetDesign()}
              >
                대상 설계 다시 불러오기
              </button>
            ) : null}
            <label className="consent-check">
              <input
                type="checkbox"
                checked={scopeConfirmed}
                disabled={busy || targetStale}
                onChange={(event) =>
                  setConfirmedReviewIdentity(
                    event.target.checked ? reviewIdentity : null,
                  )
                }
              />
              <span>
                제안 {proposal.digest.slice(0, 12)}, 워크플로 범위{" "}
                {session.scope ?? "미선택"}, 위 대상 다이제스트를 함께 검토했습니다.
                이는 이후 설계 승인과 다릅니다.
              </span>
            </label>
            <button
              className="button-primary"
              type="button"
              disabled={!scopeConfirmed || busy || targetStale}
              onClick={() => void applyProposal()}
            >
              정확한 제안 적용
            </button>
          </section>
        </>
      ) : null}

      <section className="workspace-panel danger-panel">
        <div>
          <p className="eyebrow">보존 관리</p>
          <h2>인터뷰 삭제</h2>
          <p className="muted">
            대화와 미적용 제안을 삭제합니다. 이미 적용한 설계는 유지됩니다.
          </p>
        </div>
        {deleteArmed ? (
          <div className="actions-row">
            <button
              className="button-danger"
              type="button"
              disabled={busy}
              onClick={() => void deleteInterview()}
            >
              인터뷰 영구 삭제
            </button>
            <button
              className="button-secondary"
              type="button"
              disabled={busy}
              onClick={() => setDeleteArmed(false)}
            >
              취소
            </button>
          </div>
        ) : (
          <button
            className="button-secondary"
            type="button"
            disabled={busy}
            onClick={() => setDeleteArmed(true)}
          >
            삭제 확인
          </button>
        )}
      </section>
    </div>
  );
}
