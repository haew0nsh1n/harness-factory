"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import {
  InterviewWorkspace,
  type EvidenceItem,
} from "@/components/studio/InterviewWorkspace";
import { AnswerComposer } from "@/components/studio/AnswerComposer";
import {
  DEFAULT_SELECTED_STAGES,
  InterviewStartForm,
} from "@/components/studio/InterviewStartForm";
import { OperationStatus } from "@/components/studio/OperationStatus";
import { SelectedStagesProvider } from "@/components/studio/StageProgress";
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
import { type TranslateFn } from "@/i18n/dictionaries";
import { useLocale, useTranslations } from "@/i18n/I18nProvider";
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
const RESUME_POLL_DELAYS = [10_000, 20_000, 30_000] as const;

function requestId(): string {
  if (typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function composerKey(interviewId: string): string {
  return `hf-interview-composer:${interviewId}`;
}

function selectedStagesFor(session: InterviewSession): string[] {
  return session.selected_stages?.length
    ? session.selected_stages
    : ["discovery", "planning", "implementation", "testing", "review", "release", "operations"];
}

function isTextAnswer(
  operation: AnswerOperationEnvelope,
): operation is Extract<AnswerOperationEnvelope, { answer: string }> {
  return "answer" in operation;
}

function currentQuestion(session: InterviewSession) {
  const latest = session.turns.at(-1);
  return latest?.role === "assistant" ? latest : null;
}

function hasActiveRunningOperation(session: InterviewSession | null): boolean {
  return (
    session?.last_operation?.status === "running" &&
    session.last_operation.lease_expired !== true
  );
}

function hasExpiredRunningOperation(session: InterviewSession | null): boolean {
  return (
    session?.last_operation?.status === "running" &&
    session.last_operation.lease_expired === true
  );
}

function describeApiError(cause: unknown, t: TranslateFn): string {
  if (!(cause instanceof ApiError)) {
    return t("interview.networkError");
  }
  const key = `interview.errors.${cause.code}`;
  const translated = t(key);
  return translated === key ? t("interview.genericError") : translated;
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

function formatDate(value: string, locale: string): string {
  return new Date(value).toLocaleString(locale === "ko" ? "ko-KR" : "en-US");
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
  const t = useTranslations();
  const locale = useLocale();
  const safeError = (cause: unknown) => describeApiError(cause, t);
  const [session, setSession] = useState<InterviewSession | null>(null);
  const [designs, setDesigns] = useState<HarnessDesign[]>([]);
  const [name, setName] = useState("");
  const [customerId, setCustomerId] = useState("");
  const [consented, setConsented] = useState(false);
  const [selectedStages, setSelectedStages] = useState<string[]>([
    ...DEFAULT_SELECTED_STAGES,
  ]);
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
  const [activeOperationKind, setActiveOperationKind] = useState<string | null>(
    null,
  );
  const [resumePollAttempt, setResumePollAttempt] = useState(0);
  const [resumePollingExhausted, setResumePollingExhausted] = useState(false);
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
        setSelectedStages(stored.selected_stages ?? [...DEFAULT_SELECTED_STAGES]);
      }
      return;
    }
    terminal.current = false;
    setAnswer(window.sessionStorage.getItem(composerKey(interviewId)) ?? "");
    setAnswerOperation(readAnswerOperation(interviewId));
    setProposalOperation(readProposalOperation(interviewId));
    setResumePollAttempt(0);
    setResumePollingExhausted(false);
    setError(null);
    void loadSession();
    void loadDesigns();
  }, [interviewId]);

  useEffect(() => {
    if (
      !interviewId ||
      !hasActiveRunningOperation(session) ||
      resumePollingExhausted
    ) {
      return;
    }
    const delay = RESUME_POLL_DELAYS[resumePollAttempt];
    if (delay === undefined) {
      return;
    }
    const timer = window.setTimeout(() => {
      void (async () => {
        const loaded = await loadSession();
        if (!alive.current || !hasActiveRunningOperation(loaded)) {
          return;
        }
        if (resumePollAttempt + 1 === RESUME_POLL_DELAYS.length) {
          setResumePollingExhausted(true);
          setError(
            t("interview.operationPending"),
          );
          return;
        }
        setResumePollAttempt((attempt) => attempt + 1);
      })();
    }, delay);
    return () => window.clearTimeout(timer);
  }, [
    interviewId,
    resumePollAttempt,
    resumePollingExhausted,
    session?.last_operation?.request_id,
    session?.last_operation?.status,
    session?.last_operation?.lease_expired,
  ]);

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
      t("interview.expiredOrDeleted"),
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
    if (!isTextAnswer(stored)) {
      return;
    }
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
          t("interview.proposalDigestMismatch"),
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

  async function loadSession(): Promise<InterviewSession | null> {
    if (!interviewId) {
      return null;
    }
    try {
      const loaded = await api<InterviewSession>(`/interviews/${interviewId}`);
      if (!alive.current) {
        return null;
      }
      setSession(loaded);
      if (!hasActiveRunningOperation(loaded)) {
        setResumePollAttempt(0);
        setResumePollingExhausted(false);
        setError(
          hasExpiredRunningOperation(loaded)
            ? t("interview.leaseExpired")
            : loaded.last_operation?.status === "failed"
            ? t("interview.operationFailed")
            : null,
        );
      }
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
      return loaded;
    } catch (cause) {
      if (!alive.current) {
        return null;
      }
      if (cause instanceof ApiError && cause.status === 404) {
        handleTerminalNotFound(interviewId);
      } else {
        setError(safeError(cause));
      }
      return null;
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
      setError(t("interview.nameCustomerRequired"));
      return;
    }
    if (selectedStages.length === 0) {
      setError(t("interviewStart.minStage"));
      return;
    }
    const existing = startOperation ?? readStartOperation();
    const operation =
      existing &&
      existing.name === normalizedName &&
      existing.customer_id === normalizedCustomerId &&
      JSON.stringify(existing.selected_stages) === JSON.stringify(selectedStages)
        ? existing
        : {
            name: normalizedName,
            customer_id: normalizedCustomerId,
            consent_version: CONSENT_VERSION,
            consent_accepted: true as const,
            language: locale,
            selected_stages: selectedStages,
            request_id: requestId(),
          };
    setStartOperation(operation);
    writeStartOperation(operation);
    setBusy(true);
    setActiveOperationKind("start");
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
      setActiveOperationKind(null);
    }
  }

  async function sendAnswer(retry = false): Promise<void> {
    if (!session || mutationBusy) {
      return;
    }
    const operation = retry
      ? answerOperation
      : {
          expected_revision: session.revision,
          request_id: requestId(),
          answer: answer.trim(),
        };
    if (!operation || !isTextAnswer(operation) || !operation.answer) {
      return;
    }

    setAnswerOperation(operation);
    writeAnswerOperation(session.id, operation);
    setBusy(true);
    setActiveOperationKind("answer");
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
      setActiveOperationKind(null);
    }
  }

  async function sendChoice(
    questionTurnId: string,
    optionId: string,
    retry = false,
  ): Promise<void> {
    if (!session || mutationBusy) {
      return;
    }
    const operation = retry
      ? answerOperation
      : {
          expected_revision: session.revision,
          request_id: requestId(),
          choice_answer: {
            question_turn_id: questionTurnId,
            option_id: optionId,
          },
        };
    if (
      !operation ||
      isTextAnswer(operation) ||
      operation.choice_answer.question_turn_id !== questionTurnId
    ) {
      return;
    }
    setAnswerOperation(operation);
    writeAnswerOperation(session.id, operation);
    setBusy(true);
    setActiveOperationKind("answer");
    setError(null);
    try {
      const updated = await api<InterviewSession>(
        `/interviews/${session.id}/turns`,
        { method: "POST", body: operation },
      );
      setSession(updated);
      clearAnswerOperation(session.id);
      setAnswerOperation(null);
    } catch (cause) {
      if (!handleSessionFailure(cause, session.id)) {
        setError(safeError(cause));
      }
    } finally {
      setBusy(false);
      setActiveOperationKind(null);
    }
  }

  async function decideEvidence(
    evidenceId: string,
    decision: "confirm" | "reject",
  ): Promise<void> {
    if (!session || mutationBusy) {
      return;
    }
    setBusy(true);
    setActiveOperationKind("confirmation");
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
      setActiveOperationKind(null);
    }
  }

  async function generateProposal(): Promise<void> {
    if (!session || mutationBusy) {
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
    setActiveOperationKind("proposal");
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
      setActiveOperationKind(null);
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
    setActiveOperationKind("apply");
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
      mutationBusy
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
          language: locale,
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
      setActiveOperationKind(null);
    }
  }

  async function reloadTargetDesign(): Promise<void> {
    if (!targetDesign || busy) {
      return;
    }
    setBusy(true);
    setActiveOperationKind("delete");
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
      setActiveOperationKind(null);
    }
  }

  async function deleteInterview(): Promise<void> {
    if (!session || mutationBusy) {
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
  const activeRunning = hasActiveRunningOperation(session);
  const mutationBusy = busy || activeRunning;
  const pendingOperationKind =
    busy
      ? activeOperationKind
      : activeRunning
        ? (session?.last_operation?.kind ?? null)
        : null;

  if (!interviewId) {
    return (
      <div className="page-stack">
        <header className="page-intro">
          <p className="eyebrow">{t("interview.newInterviewEyebrow")}</p>
          <h1 className="workspace-heading">{t("interview.startHeading")}</h1>
          <p className="page-description">{t("interview.startIntro")}</p>
        </header>
        <OperationStatus kind={busy ? "start" : null} />
        <InterviewStartForm
          name={name}
          customerId={customerId}
          consented={consented}
          selectedStages={selectedStages}
          busy={busy}
          error={error}
          onNameChange={setName}
          onCustomerIdChange={setCustomerId}
          onConsentChange={setConsented}
          onSelectedStagesChange={setSelectedStages}
          onStart={() => void startInterview()}
        />
      </div>
    );
  }

  if (!session) {
    return (
      <section className="workspace-panel state-panel" aria-busy={!error}>
        <p className={error ? "error-text" : "muted"}>
          {error ?? t("interview.loading")}
        </p>
        {error ? (
          <a className="button-secondary" href="/studio/interviews/new">
            {t("interview.newInterviewBtn")}
          </a>
        ) : null}
      </section>
    );
  }

  return (
    <div className="page-stack" aria-busy={mutationBusy}>
      <section className="workspace-panel interview-session-header">
        <div className="page-header">
          <div>
            <p className="eyebrow">{t("interview.sessionEyebrow", { revision: session.revision })}</p>
            <h1 className="workspace-heading">{session.name}</h1>
            <p className="page-description">
              {t("interview.savedAt", { customer: session.customer_id, updated: formatDate(session.updated_at, locale) })}
              {t("interview.expiresAt", { expires: formatDate(session.expires_at, locale) })}
            </p>
          </div>
          <a className="button-secondary" href="/studio">
            {t("interview.toStudio")}
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
              {t("interview.reloadLatest")}
            </button>
          </div>
        ) : null}
      </section>

      <OperationStatus
        kind={pendingOperationKind}
        recovering={!busy && activeRunning}
      />
      <SelectedStagesProvider stages={selectedStagesFor(session)}>
        <InterviewWorkspace
        title={session.name}
        stage={session.stage}
        evidence={evidence}
        onConfirm={
          mutationBusy ? undefined : (id) => void decideEvidence(id, "confirm")
        }
        boundary={t("interview.boundary")}
        conversation={
          <div className="turn-list" aria-live="polite">
            {session.turns.map((turn) => (
              <article
                className={`interview-turn turn-${turn.role}`}
                id={`turn-${turn.id}`}
                key={turn.id}
              >
                <p className="turn-role">
                  {turn.role === "assistant" ? t("interview.questionLabel") : t("interview.answerLabel")}
                </p>
                <p>{turn.text}</p>
              </article>
            ))}
          </div>
        }
        composer={
          <AnswerComposer
            question={currentQuestion(session)}
            answer={answer}
            busy={mutationBusy}
            retryAvailable={Boolean(answerOperation)}
            onAnswerChange={setAnswer}
            onSendAnswer={() => void sendAnswer(false)}
            onSendChoice={(questionTurnId, optionId) =>
              void sendChoice(questionTurnId, optionId)
            }
            onRetry={() => {
              if (!answerOperation) {
                return;
              }
              if (isTextAnswer(answerOperation)) {
                void sendAnswer(true);
              } else {
                void sendChoice(
                  answerOperation.choice_answer.question_turn_id,
                  answerOperation.choice_answer.option_id,
                  true,
                );
              }
            }}
            />
        }
      />
      </SelectedStagesProvider>

      {session.proposed_evidence.length > 0 ? (
        <section className="workspace-panel">
          <p className="eyebrow">{t("interview.humanConfirmEyebrow")}</p>
          <h2>{t("interview.proposedEvidenceHeading")}</h2>
          {session.proposed_evidence.map((item) => (
            <div className="review-row" key={item.id}>
              <p>{item.statement}</p>
              <div className="actions-row">
                <button
                  className="button-secondary"
                  type="button"
                  disabled={mutationBusy}
                  onClick={() => void decideEvidence(item.id, "confirm")}
                >
                  {t("evidence.confirmFact")}
                </button>
                <button
                  className="button-secondary"
                  type="button"
                  disabled={mutationBusy}
                  onClick={() => void decideEvidence(item.id, "reject")}
                >
                  {t("interview.rejectEvidence")}
                </button>
              </div>
            </div>
          ))}
        </section>
      ) : null}

      <section className="workspace-panel proposal-action">
        <div>
          <p className="eyebrow">{t("interview.explicitProposalEyebrow")}</p>
          <h2>{t("interview.makeProposalHeading")}</h2>
          <p className="muted">{t("interview.proposalHint")}</p>
        </div>
        <button
          className="button-primary"
          type="button"
          disabled={mutationBusy}
          onClick={() => void generateProposal()}
        >
          {proposalOperation ? t("interview.retryProposal") : t("interview.generateProposal")}
        </button>
      </section>

      {session.proposals.length > 0 ? (
        <section className="workspace-panel">
          <label className="field">
            <span>{t("interview.savedProposalLabel")}</span>
            <select
              aria-label={t("interview.savedProposalLabel")}
              value={proposal?.id ?? ""}
              disabled={mutationBusy}
              onChange={(event) => void selectProposal(event.target.value)}
            >
              {session.proposals.map((item) => (
                <option value={item.id} key={item.id}>
                  {t("interview.proposalOption", { revision: item.revision, status: item.status, digest: item.digest.slice(0, 12) })}
                </option>
              ))}
            </select>
          </label>
        </section>
      ) : null}

      {proposal && proposalDraft ? (
        <>
          <section className="workspace-panel proposal-review-header">
            <p className="eyebrow">{t("interview.exactProposalEyebrow")}</p>
            <h2>{t("interview.proposalDigestHeading")}</h2>
            <code className="digest-text">{proposal.digest}</code>
            <p>{t("interview.proposalReadonlyNote")}</p>
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
              <span>{t("interview.applyTarget")}</span>
              <select
                aria-label={t("interview.applyTarget")}
                value={targetDesignId}
                disabled={mutationBusy}
                onChange={(event) => {
                  setTargetDesignId(event.target.value);
                  setTargetStale(false);
                }}
              >
                <option value={NEW_DESIGN}>{t("interview.newDesignOption")}</option>
                {designs
                  .filter((design) => design.language === locale)
                  .map((design) => (
                    <option value={design.id} key={design.id}>
                      {t("interview.existingDesignOption", { name: design.name })}
                    </option>
                  ))}
              </select>
            </label>
            <p className="muted">
              {t("interview.targetCurrentDigest")}
              <code>{targetDesign?.digest ?? t("interview.noExistingDigest")}</code>
            </p>
            {targetStale && targetDesign ? (
              <button
                className="button-secondary"
                type="button"
                disabled={busy}
                onClick={() => void reloadTargetDesign()}
              >
                {t("interview.reloadTargetDesign")}
              </button>
            ) : null}
            <label className="consent-check">
              <input
                type="checkbox"
                checked={scopeConfirmed}
                disabled={mutationBusy || targetStale}
                onChange={(event) =>
                  setConfirmedReviewIdentity(
                    event.target.checked ? reviewIdentity : null,
                  )
                }
              />
              <span>
                {t("interview.reviewSummary", { digest: proposal.digest.slice(0, 12), scope: session.scope ?? t("interview.scopeUnselected") })}
              </span>
            </label>
            <button
              className="button-primary"
              type="button"
              disabled={!scopeConfirmed || mutationBusy || targetStale}
              onClick={() => void applyProposal()}
            >
              {t("interview.applyExactProposal")}
            </button>
          </section>
        </>
      ) : null}

      <section className="workspace-panel danger-panel">
        <div>
          <p className="eyebrow">{t("interview.retentionEyebrow")}</p>
          <h2>{t("interview.deleteHeading")}</h2>
          <p className="muted">{t("interview.deleteNote")}</p>
        </div>
        {deleteArmed ? (
          <div className="actions-row">
            <button
              className="button-danger"
              type="button"
              disabled={mutationBusy}
              onClick={() => void deleteInterview()}
            >
              {t("interview.deletePermanently")}
            </button>
            <button
              className="button-secondary"
              type="button"
              disabled={mutationBusy}
              onClick={() => setDeleteArmed(false)}
            >
              {t("interview.cancel")}
            </button>
          </div>
        ) : (
          <button
            className="button-secondary"
            type="button"
            disabled={mutationBusy}
            onClick={() => setDeleteArmed(true)}
          >
            {t("interview.confirmDelete")}
          </button>
        )}
      </section>
    </div>
  );
}
