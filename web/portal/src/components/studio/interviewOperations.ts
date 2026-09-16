export interface StartOperationEnvelope {
  request_id: string;
  name: string;
  customer_id: string;
  consent_version: "2026-09-15";
  consent_accepted: true;
  selected_stages: string[];
}

interface BaseAnswerOperationEnvelope {
  request_id: string;
  expected_revision: number;
}

export interface TextAnswerOperationEnvelope extends BaseAnswerOperationEnvelope {
  answer: string;
}

export interface ChoiceAnswerOperationEnvelope extends BaseAnswerOperationEnvelope {
  choice_answer: {
    question_turn_id: string;
    option_id: string;
  };
}

export type AnswerOperationEnvelope =
  | TextAnswerOperationEnvelope
  | ChoiceAnswerOperationEnvelope;

export interface ProposalOperationEnvelope {
  request_id: string;
  expected_revision: number;
}

const START_KEY = "hf-interview-start-operation";

function operationKey(
  interviewId: string,
  kind: "answer" | "proposal" | "selected-proposal",
): string {
  return `hf-interview-${kind}:${interviewId}`;
}

function readJson<T>(key: string): T | null {
  const value = window.sessionStorage.getItem(key);
  if (!value) {
    return null;
  }
  try {
    return JSON.parse(value) as T;
  } catch {
    window.sessionStorage.removeItem(key);
    return null;
  }
}

function writeJson(key: string, value: object): void {
  window.sessionStorage.setItem(key, JSON.stringify(value));
}

export function readStartOperation(): StartOperationEnvelope | null {
  return readJson<StartOperationEnvelope>(START_KEY);
}

export function writeStartOperation(value: StartOperationEnvelope): void {
  writeJson(START_KEY, value);
}

export function clearStartOperation(): void {
  window.sessionStorage.removeItem(START_KEY);
}

export function readAnswerOperation(
  interviewId: string,
): AnswerOperationEnvelope | null {
  return readJson<AnswerOperationEnvelope>(operationKey(interviewId, "answer"));
}

export function writeAnswerOperation(
  interviewId: string,
  value: AnswerOperationEnvelope,
): void {
  writeJson(operationKey(interviewId, "answer"), value);
}

export function clearAnswerOperation(interviewId: string): void {
  window.sessionStorage.removeItem(operationKey(interviewId, "answer"));
}

export function readProposalOperation(
  interviewId: string,
): ProposalOperationEnvelope | null {
  return readJson<ProposalOperationEnvelope>(
    operationKey(interviewId, "proposal"),
  );
}

export function writeProposalOperation(
  interviewId: string,
  value: ProposalOperationEnvelope,
): void {
  writeJson(operationKey(interviewId, "proposal"), value);
}

export function clearProposalOperation(interviewId: string): void {
  window.sessionStorage.removeItem(operationKey(interviewId, "proposal"));
}

export function readSelectedProposal(interviewId: string): string | null {
  return window.sessionStorage.getItem(
    operationKey(interviewId, "selected-proposal"),
  );
}

export function writeSelectedProposal(
  interviewId: string,
  proposalId: string,
): void {
  window.sessionStorage.setItem(
    operationKey(interviewId, "selected-proposal"),
    proposalId,
  );
}

export function clearInterviewOperations(interviewId: string): void {
  clearAnswerOperation(interviewId);
  clearProposalOperation(interviewId);
  window.sessionStorage.removeItem(
    operationKey(interviewId, "selected-proposal"),
  );
  window.sessionStorage.removeItem(`hf-interview-request:${interviewId}`);
}
