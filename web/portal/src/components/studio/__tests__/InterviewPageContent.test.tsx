import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { InterviewPageContent } from "@/components/studio/InterviewPageContent";
import type { InterviewSession } from "@/lib/types";
import catalogExample from "../../../../../../catalog/catalog.json";
import profileExample from "../../../../../../examples/github-issue/profile.json";
import scenariosExample from "../../../../../../examples/github-issue/scenarios.json";
import workflowExample from "../../../../../../examples/github-issue/workflow.json";

function response(body: object, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

const session: InterviewSession = {
  id: "interview-1",
  organization_id: "org-acme",
  owner_subject_id: "author-1",
  name: "Acme delivery",
  customer_id: "acme",
  revision: 2,
  status: "awaiting-confirmation" as const,
  consent_version: "2026-09-15",
  consented_at: "2026-09-15T00:00:00Z",
  stage: "planning" as const,
  scope: "review-handoff",
  proposed_evidence: [
    {
      id: "evidence-1",
      statement: "리뷰는 수동 인계를 기다립니다.",
      kind: "fact" as const,
      source_turn_ids: ["turn-user", "turn-context"],
    },
  ],
  confirmed_evidence: [],
  turns: [
    {
      id: "turn-assistant",
      role: "assistant" as const,
      text: "어디에서 작업이 가장 오래 멈추나요?",
      sequence: 1,
      created_at: "2026-09-15T00:00:00Z",
    },
    {
      id: "turn-user",
      role: "user" as const,
      text: "리뷰 인계에서 멈춥니다.",
      sequence: 2,
      created_at: "2026-09-15T00:01:00Z",
    },
    {
      id: "turn-context",
      role: "user" as const,
      text: "두 번째 근거입니다.",
      sequence: 3,
      created_at: "2026-09-15T00:02:00Z",
    },
  ],
  proposals: [],
  last_operation: null,
  last_error_code: null,
  created_at: "2026-09-15T00:00:00Z",
  updated_at: "2026-09-15T00:01:00Z",
  expires_at: "2026-10-15T00:01:00Z",
};

const proposal = {
  id: "proposal-1",
  revision: 3,
  digest: "a".repeat(64),
  status: "draft",
  findings: [{ code: "scope-confirmation-required", message: "confirm" }],
  profile: profileExample,
  workflow: workflowExample,
  scenarios: scenariosExample,
  catalog: catalogExample,
  created_at: "2026-09-15T00:02:00Z",
  updated_at: "2026-09-15T00:02:00Z",
};

const proposalSummary = {
  id: proposal.id,
  revision: proposal.revision,
  digest: proposal.digest,
  status: proposal.status,
  findings: proposal.findings,
  created_at: proposal.created_at,
  updated_at: proposal.updated_at,
};

const design = {
  id: "design-1",
  organization_id: "org-acme",
  customer_id: "acme",
  name: "Current Acme design",
  language: "ko" as const,
  profile: profileExample,
  workflow: workflowExample,
  scenarios: scenariosExample,
  catalog: catalogExample,
  revision: 4,
  digest: "b".repeat(64),
  status: "approved" as const,
  validation_findings: [],
  created_by: "author-1",
  created_at: "2026-09-14T00:00:00Z",
  updated_at: "2026-09-15T00:00:00Z",
};

function installFetch(
  handler: (path: string, init?: RequestInit) => Response | Promise<Response>,
) {
  return vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
    return Promise.resolve(handler(String(input), init));
  });
}

function installLoadedSession(
  value = session,
  designs = [] as object[],
) {
  return installFetch((path) => {
    if (path === "/api/control-plane/interviews/interview-1") {
      return response({ ok: true, session: value });
    }
    if (path === "/api/control-plane/designs") {
      return response({ ok: true, items: designs });
    }
    throw new Error(`Unexpected request: ${path}`);
  });
}

describe("InterviewPageContent lifecycle", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    window.sessionStorage.clear();
  });

  test("requires consent, makes no call while typing, and starts changed input with a new envelope", async () => {
    const bodies: Array<Record<string, unknown>> = [];
    installFetch((path, init) => {
      expect(path).toBe("/api/control-plane/interviews");
      bodies.push(JSON.parse(String(init?.body)));
      return response(
        { ok: false, code: "llm_timeout", error: "timed out" },
        503,
      );
    });

    render(<InterviewPageContent />);

    fireEvent.change(screen.getByLabelText("인터뷰 이름"), {
      target: { value: "첫 인터뷰" },
    });
    fireEvent.change(screen.getByLabelText("고객 ID"), {
      target: { value: "acme" },
    });
    expect(globalThis.fetch).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "인터뷰 시작" })).toBeDisabled();

    fireEvent.click(screen.getByRole("checkbox", { name: /Azure OpenAI/ }));
    fireEvent.click(screen.getByRole("button", { name: "인터뷰 시작" }));
    await screen.findByRole("alert");
    fireEvent.click(screen.getByRole("button", { name: "인터뷰 시작" }));
    await waitFor(() => expect(bodies).toHaveLength(2));
    expect(bodies[1]).toEqual(bodies[0]);

    fireEvent.change(screen.getByLabelText("인터뷰 이름"), {
      target: { value: "변경한 인터뷰" },
    });
    fireEvent.click(screen.getByRole("button", { name: "인터뷰 시작" }));
    await waitFor(() => expect(bodies).toHaveLength(3));
    expect(bodies[2]?.request_id).not.toBe(bodies[0]?.request_id);
    expect(bodies[2]?.name).toBe("변경한 인터뷰");
  });

  test("sends the default stage subset, prevents an empty subset, and changes the start request for a new subset", async () => {
    const bodies: Array<Record<string, unknown>> = [];
    installFetch((path, init) => {
      expect(path).toBe("/api/control-plane/interviews");
      bodies.push(JSON.parse(String(init?.body)));
      return response({ ok: false, code: "llm_timeout", error: "timed out" }, 503);
    });
    render(<InterviewPageContent />);
    fireEvent.change(screen.getByLabelText("인터뷰 이름"), { target: { value: "단계 선택" } });
    fireEvent.change(screen.getByLabelText("고객 ID"), { target: { value: "acme" } });
    fireEvent.click(screen.getByRole("checkbox", { name: /Azure OpenAI/ }));
    fireEvent.click(screen.getByRole("button", { name: "인터뷰 시작" }));
    await screen.findByRole("alert");
    expect(bodies[0]?.selected_stages).toEqual(["planning", "implementation", "review"]);
    fireEvent.click(screen.getByRole("button", { name: "선택 해제" }));
    expect(screen.getByRole("button", { name: "인터뷰 시작" })).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox", { name: "발견" }));
    fireEvent.click(screen.getByRole("button", { name: "인터뷰 시작" }));
    await waitFor(() => expect(bodies).toHaveLength(2));
    expect(bodies[1]).toMatchObject({ selected_stages: ["discovery"] });
    expect(bodies[1]?.request_id).not.toBe(bodies[0]?.request_id);
  });

  test("shows interview API failures in Korean instead of exposing English server copy", async () => {
    installFetch(() =>
      response(
        {
          ok: false,
          code: "scope_not_selected",
          error: "workflow scope has not been selected",
        },
        409,
      ),
    );
    render(<InterviewPageContent />);

    fireEvent.change(screen.getByLabelText("인터뷰 이름"), {
      target: { value: "범위 확인" },
    });
    fireEvent.change(screen.getByLabelText("고객 ID"), {
      target: { value: "acme" },
    });
    fireEvent.click(screen.getByRole("checkbox", { name: /Azure OpenAI/ }));
    fireEvent.click(screen.getByRole("button", { name: "인터뷰 시작" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "워크플로우 범위가 아직 선택되지 않았습니다.",
    );
    expect(screen.getByRole("alert")).not.toHaveTextContent(
      "workflow scope has not been selected",
    );
  });

  test("advises continuing the interview when a persisted scope is malformed", async () => {
    installFetch((path, init) => {
      if (path === "/api/control-plane/interviews/interview-1") {
        return response({ ok: true, session });
      }
      if (path === "/api/control-plane/designs") {
        return response({ ok: true, items: [] });
      }
      if (path.endsWith("/proposals") && init?.method === "POST") {
        return response(
          {
            ok: false,
            code: "scope_invalid",
            error: "selected scope is not a canonical workflow ID",
          },
          409,
        );
      }
      throw new Error(`Unexpected request: ${path}`);
    });
    render(<InterviewPageContent interviewId="interview-1" />);

    fireEvent.click(
      await screen.findByRole("button", { name: "디자인 제안 생성" }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "인터뷰를 계속해 새 워크플로우 범위를 확정",
    );
    expect(screen.getByRole("alert")).not.toHaveTextContent(
      "selected scope is not a canonical workflow ID",
    );
  });

  test("retries the immutable answer envelope and uses a new id for edited input", async () => {
    const answerBodies: Array<Record<string, unknown>> = [];
    installFetch((path, init) => {
      if (path === "/api/control-plane/interviews/interview-1") {
        return response({ ok: true, session });
      }
      if (path === "/api/control-plane/designs") {
        return response({ ok: true, items: [] });
      }
      if (path.endsWith("/turns")) {
        answerBodies.push(JSON.parse(String(init?.body)));
        if (answerBodies.length === 2) {
          return response({
            ok: true,
            session: { ...session, revision: 3 },
          });

        }
        return response(
          { ok: false, code: "llm_timeout", error: "timed out" },
          503,
        );
      }
      throw new Error(`Unexpected request: ${path}`);
    });
    render(<InterviewPageContent interviewId="interview-1" />);

    const composer = await screen.findByLabelText("답변");
    fireEvent.change(composer, { target: { value: "첫 답변" } });
    fireEvent.click(screen.getByRole("button", { name: "답변 보내기" }));
    await screen.findByRole("alert");
    fireEvent.click(
      screen.getByRole("button", { name: "저장된 요청 다시 시도" }),
    );
    await waitFor(() => expect(answerBodies).toHaveLength(2));
    expect(answerBodies[1]).toEqual(answerBodies[0]);

    fireEvent.change(composer, { target: { value: "새 답변" } });
    fireEvent.click(screen.getByRole("button", { name: "답변 보내기" }));
    await waitFor(() => expect(answerBodies).toHaveLength(3));
    expect(answerBodies[2]?.request_id).not.toBe(answerBodies[0]?.request_id);
    expect(answerBodies[2]).toMatchObject({
      expected_revision: 3,
      answer: "새 답변",
    });
  });

  test("sends an AI suggestion only after explicit submission and preserves its immutable retry", async () => {
    const answerBodies: Array<Record<string, unknown>> = [];
    const suggested = {
      ...session,
      turns: [{
        ...session.turns[0],
        options: [{ id: "review-first", label: "리뷰 기준을 먼저 합의합니다." }],
        allow_custom_answer: true,
      }],
    };
    installFetch((path, init) => {
      if (path === "/api/control-plane/interviews/interview-1") return response({ ok: true, session: suggested });
      if (path === "/api/control-plane/designs") return response({ ok: true, items: [] });
      if (path.endsWith("/turns")) {
        answerBodies.push(JSON.parse(String(init?.body)));
        return response({ ok: false, code: "llm_timeout", error: "timed out" }, 503);
      }
      throw new Error(`Unexpected request: ${path}`);
    });
    render(<InterviewPageContent interviewId="interview-1" />);
    fireEvent.click(await screen.findByRole("radio", { name: "리뷰 기준을 먼저 합의합니다." }));
    expect(answerBodies).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "답변 보내기" }));
    await screen.findByRole("alert");
    expect(answerBodies[0]).toEqual({
      expected_revision: 2,
      request_id: expect.any(String),
      choice_answer: { question_turn_id: "turn-assistant", option_id: "review-first" },
    });
    fireEvent.click(screen.getByRole("button", { name: "저장된 요청 다시 시도" }));
    await waitFor(() => expect(answerBodies).toHaveLength(2));
    expect(answerBodies[1]).toEqual(answerBodies[0]);
  });

  test("shows persisted in-progress work and disables all confirmation controls", async () => {
    installLoadedSession({
      ...session,
      selected_stages: ["planning", "review"],
      proposed_evidence: [
        {
          id: "evidence-1",
          statement: "검토 기준을 확인합니다.",
          kind: "fact",
          source_turn_ids: ["turn-assistant"],
        },
      ],
      last_operation: {
        request_id: "11111111-1111-4111-8111-111111111111",
        kind: "answer",
        status: "running",
      },
    });
    render(<InterviewPageContent interviewId="interview-1" />);
    expect(await screen.findByRole("status")).toHaveTextContent("저장된 작업 상태를 확인");
    expect(screen.getByLabelText("답변")).toBeDisabled();
    expect(screen.getByRole("button", { name: "디자인 제안 생성" })).toBeDisabled();
    const confirmation = screen.getByRole("button", { name: "사실 확인" });
    expect(confirmation).toBeDisabled();
    fireEvent.click(confirmation);
    expect(globalThis.fetch).toHaveBeenCalledTimes(2);
  });

  test("unlocks an expired persisted operation and retries its immutable saved answer", async () => {
    const envelope = {
      request_id: "11111111-1111-4111-8111-111111111111",
      expected_revision: 2,
      answer: "임대 만료 전에 저장한 답변",
    };
    window.sessionStorage.setItem(
      "hf-interview-answer:interview-1",
      JSON.stringify(envelope),
    );
    const answerBodies: Array<Record<string, unknown>> = [];
    installFetch((path, init) => {
      if (path === "/api/control-plane/interviews/interview-1") {
        return response({
          ok: true,
          session: {
            ...session,
            last_operation: {
              request_id: envelope.request_id,
              kind: "answer",
              status: "running",
              lease_expired: true,
            },
          },
        });
      }
      if (path === "/api/control-plane/designs") {
        return response({ ok: true, items: [] });
      }
      if (path.endsWith("/turns")) {
        answerBodies.push(JSON.parse(String(init?.body)));
        return response({ ok: true, session: { ...session, revision: 3 } });
      }
      throw new Error(`Unexpected request: ${path}`);
    });

    render(<InterviewPageContent interviewId="interview-1" />);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "이전 작업의 실행 임대가 만료되어 중단되었습니다.",
    );
    expect(screen.getByLabelText("답변")).not.toBeDisabled();
    fireEvent.click(
      screen.getByRole("button", { name: "저장된 요청 다시 시도" }),
    );
    await waitFor(() => expect(answerBodies).toHaveLength(1));
    expect(answerBodies[0]).toEqual(envelope);
  });

  test("offers a fresh proposal action when an expired operation has no saved client envelope", async () => {
    const proposalBodies: Array<Record<string, unknown>> = [];
    installFetch((path, init) => {
      if (path === "/api/control-plane/interviews/interview-1") {
        return response({
          ok: true,
          session: {
            ...session,
            last_operation: {
              request_id: "11111111-1111-4111-8111-111111111111",
              kind: "proposal",
              status: "running",
              lease_expired: true,
            },
          },
        });
      }
      if (path === "/api/control-plane/designs") {
        return response({ ok: true, items: [] });
      }
      if (path.endsWith("/proposals")) {
        proposalBodies.push(JSON.parse(String(init?.body)));
        return response(
          { ok: false, code: "llm_timeout", error: "timed out" },
          503,
        );
      }
      throw new Error(`Unexpected request: ${path}`);
    });

    render(<InterviewPageContent interviewId="interview-1" />);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "이전 작업의 실행 임대가 만료되어 중단되었습니다.",
    );
    expect(
      screen.queryByRole("button", { name: "저장된 요청 다시 시도" }),
    ).not.toBeInTheDocument();
    const generateButton = screen.getByRole("button", {
      name: "디자인 제안 생성",
    });
    expect(generateButton).toBeEnabled();
    fireEvent.click(generateButton);
    await waitFor(() => expect(proposalBodies).toHaveLength(1));
    expect(proposalBodies[0]).toEqual({
      expected_revision: session.revision,
      request_id: expect.not.stringMatching(
        "11111111-1111-4111-8111-111111111111",
      ),
    });
  });

  test("keeps a failed choice retry immutable while new input follows the latest question", async () => {
    const answerBodies: Array<Record<string, unknown>> = [];
    const oldQuestion = {
      ...session.turns[0],
      id: "old-question",
      options: [{ id: "old-option", label: "이전 제안" }],
    };
    const newQuestion = {
      ...session.turns[0],
      id: "new-question",
      options: [{ id: "new-option", label: "최신 제안" }],
    };
    let sessionLoads = 0;
    installFetch((path, init) => {
      if (path === "/api/control-plane/interviews/interview-1") {
        sessionLoads += 1;
        return response({
          ok: true,
          session: {
            ...session,
            turns: [sessionLoads === 1 ? oldQuestion : newQuestion],
          },
        });
      }
      if (path === "/api/control-plane/designs") return response({ ok: true, items: [] });
      if (path.endsWith("/turns")) {
        answerBodies.push(JSON.parse(String(init?.body)));
        return response(
          { ok: false, code: "choice_question_not_current", error: "stale choice" },
          409,
        );
      }
      throw new Error(`Unexpected request: ${path}`);
    });
    render(<InterviewPageContent interviewId="interview-1" />);

    fireEvent.click(await screen.findByRole("radio", { name: "이전 제안" }));
    fireEvent.click(screen.getByRole("button", { name: "답변 보내기" }));
    await screen.findByRole("alert");
    const failedBody = answerBodies[0];

    fireEvent.click(screen.getByRole("button", { name: "최신 상태 다시 불러오기" }));
    expect(await screen.findByRole("radio", { name: "최신 제안" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "저장된 요청 다시 시도" }));
    await waitFor(() => expect(answerBodies).toHaveLength(2));
    expect(answerBodies[1]).toEqual(failedBody);

    fireEvent.click(screen.getByRole("radio", { name: "최신 제안" }));
    fireEvent.click(screen.getByRole("button", { name: "답변 보내기" }));
    await waitFor(() => expect(answerBodies).toHaveLength(3));
    expect(answerBodies[2]).toMatchObject({
      choice_answer: { question_turn_id: "new-question", option_id: "new-option" },
    });
    expect(answerBodies[2]?.request_id).not.toBe(failedBody?.request_id);
  });

  test("stops polling only after the final running response and manual refresh unlocks a completed operation", async () => {
    vi.useFakeTimers();
    let completed = false;
    const running = {
      ...session,
      last_operation: {
        request_id: "11111111-1111-4111-8111-111111111111",
        kind: "answer",
        status: "running",
      },
    };
    installFetch((path) => {
      if (path === "/api/control-plane/interviews/interview-1") {
        return response({ ok: true, session: completed ? { ...session, revision: 3 } : running });
      }
      if (path === "/api/control-plane/designs") return response({ ok: true, items: [] });
      throw new Error(`Unexpected request: ${path}`);
    });
    render(<InterviewPageContent interviewId="interview-1" />);
    await act(async () => {});
    for (const delay of [10_000, 20_000, 30_000]) {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(delay);
      });
    }
    expect(screen.getByRole("alert")).toHaveTextContent("저장된 작업이 아직 완료되지 않았습니다");
    expect(screen.getByLabelText("답변")).toBeDisabled();

    completed = true;
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "최신 상태 다시 불러오기" }));
    });
    expect(screen.getByLabelText("답변")).not.toBeDisabled();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    vi.useRealTimers();
  });

  test("reconciles a succeeded answer after reload without resending it", async () => {
    const envelope = {
      request_id: "11111111-1111-4111-8111-111111111111",
      expected_revision: 2,
      answer: "응답을 잃은 답변",
    };
    window.sessionStorage.setItem(
      "hf-interview-answer:interview-1",
      JSON.stringify(envelope),
    );
    window.sessionStorage.setItem(
      "hf-interview-composer:interview-1",
      envelope.answer,
    );
    const fetchSpy = installLoadedSession({
      ...session,
      revision: 3,
      last_operation: {
        request_id: envelope.request_id,
        kind: "answer",
        status: "succeeded",
      },
    });

    render(<InterviewPageContent interviewId="interview-1" />);

    expect(await screen.findByLabelText("답변")).toHaveValue("");
    expect(
      screen.queryByRole("button", { name: "저장된 요청 다시 시도" }),
    ).not.toBeInTheDocument();
    expect(window.sessionStorage.getItem("hf-interview-answer:interview-1")).toBeNull();
    expect(fetchSpy.mock.calls.every(([, init]) => !init || init.method !== "POST")).toBe(
      true,
    );
  });

  test("locks the composer for the actual pending promise and clears only its submitted text", async () => {
    const pending = deferred<Response>();
    installFetch((path) => {
      if (path === "/api/control-plane/interviews/interview-1") {
        return response({ ok: true, session });
      }
      if (path === "/api/control-plane/designs") {
        return response({ ok: true, items: [] });
      }
      if (path.endsWith("/turns")) {
        return pending.promise;
      }
      throw new Error(`Unexpected request: ${path}`);
    });
    render(<InterviewPageContent interviewId="interview-1" />);

    const composer = await screen.findByLabelText("답변");
    fireEvent.change(composer, { target: { value: "전송 중 답변" } });
    fireEvent.click(screen.getByRole("button", { name: "답변 보내기" }));
    expect(composer).toBeDisabled();
    expect(composer).toHaveValue("전송 중 답변");
    expect(screen.getByRole("status")).toHaveTextContent("답변을 처리하고 다음 질문을 준비");

    pending.resolve(
      response({ ok: true, session: { ...session, revision: 3 } }),
    );
    await waitFor(() => expect(composer).not.toBeDisabled());
    expect(composer).toHaveValue("");
  });

  test("loads a persisted proposal detail after refresh without a model POST", async () => {
    const completed = {
      ...session,
      revision: 3,
      status: "completed" as const,
      proposals: [proposalSummary],
    };
    const fetchSpy = installFetch((path) => {
      if (path === "/api/control-plane/interviews/interview-1") {
        return response({ ok: true, session: completed });
      }
      if (path === "/api/control-plane/designs") {
        return response({ ok: true, items: [] });
      }
      if (
        path ===
        "/api/control-plane/interviews/interview-1/proposals/proposal-1"
      ) {
        return response({ ok: true, proposal });
      }
      throw new Error(`Unexpected request: ${path}`);
    });

    render(<InterviewPageContent interviewId="interview-1" />);

    expect(await screen.findByText(proposal.digest)).toBeInTheDocument();
    expect(screen.getByLabelText("프로필 전체 JSON 검토")).toHaveAttribute(
      "readonly",
    );
    expect(
      fetchSpy.mock.calls.some(
        ([path, init]) =>
          String(path).endsWith("/proposals") && init?.method === "POST",
      ),
    ).toBe(false);
  });

  test("shows the proposal action instead of the answer composer after completion", async () => {
    installLoadedSession({
      ...session,
      status: "completed",
      proposed_evidence: [],
    });

    render(<InterviewPageContent interviewId="interview-1" />);

    expect(
      await screen.findByRole("button", { name: "디자인 제안 생성" }),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("답변")).not.toBeInTheDocument();
  });

  test("binds confirmation to the exact proposal, scope, and target digest", async () => {
    const completed = {
      ...session,
      revision: 3,
      status: "completed" as const,
      proposals: [proposalSummary],
    };
    installFetch((path) => {
      if (path === "/api/control-plane/interviews/interview-1") {
        return response({ ok: true, session: completed });
      }
      if (path === "/api/control-plane/designs") {
        return response({ ok: true, items: [design] });
      }
      if (path.endsWith("/proposals/proposal-1")) {
        return response({ ok: true, proposal });
      }
      throw new Error(`Unexpected request: ${path}`);
    });
    render(<InterviewPageContent interviewId="interview-1" />);

    const confirmation = await screen.findByRole("checkbox", {
      name: /제안 aaaaaaaaaaaa/,
    });
    fireEvent.click(confirmation);
    expect(
      screen.getByRole("button", { name: "디자인 등록" }),
    ).toBeEnabled();

    fireEvent.change(screen.getByLabelText("적용 대상"), {
      target: { value: "design-1" },
    });
    expect(confirmation).not.toBeChecked();
    expect(
      screen.getByRole("button", { name: "디자인 등록" }),
    ).toBeDisabled();
    expect(screen.getByText(design.digest)).toBeInTheDocument();
  });

  test("invalidates apply confirmation when a reload changes the selected scope", async () => {
    const completed = {
      ...session,
      revision: 3,
      status: "completed" as const,
      proposals: [proposalSummary],
    };
    let sessionLoads = 0;
    installFetch((path, init) => {
      if (path === "/api/control-plane/interviews/interview-1") {
        sessionLoads += 1;
        return response({
          ok: true,
          session:
            sessionLoads === 1
              ? completed
              : { ...completed, scope: "release-handoff" },
        });
      }
      if (path === "/api/control-plane/designs") {
        return response({ ok: true, items: [] });
      }
      if (path.endsWith("/proposals/proposal-1")) {
        return response({ ok: true, proposal });
      }
      if (path.endsWith("/confirmations") && init?.method === "POST") {
        return response(
          { ok: false, code: "stale_revision", error: "stale" },
          409,
        );
      }
      throw new Error(`Unexpected request: ${path}`);
    });
    render(<InterviewPageContent interviewId="interview-1" />);

    const confirmation = await screen.findByRole("checkbox", {
      name: /제안 aaaaaaaaaaaa/,
    });
    fireEvent.click(confirmation);
    fireEvent.click(screen.getAllByRole("button", { name: "사실 확인" })[0]);
    await screen.findByRole("alert");
    fireEvent.click(
      screen.getByRole("button", { name: "최신 상태 다시 불러오기" }),
    );

    await screen.findByText(/워크플로우 범위 release-handoff/);
    expect(confirmation).not.toBeChecked();
    expect(
      screen.getByRole("button", { name: "디자인 등록" }),
    ).toBeDisabled();
  });

  test("submits the reviewed target digest and retains the proposal on stale conflict", async () => {
    const completed = {
      ...session,
      revision: 3,
      status: "completed" as const,
      proposals: [proposalSummary],
    };
    const refreshedDesign = { ...design, digest: "c".repeat(64), revision: 5 };
    let applyBody: Record<string, unknown> | null = null;
    installFetch((path, init) => {
      if (path === "/api/control-plane/interviews/interview-1") {
        return response({ ok: true, session: completed });
      }
      if (path === "/api/control-plane/designs") {
        return response({ ok: true, items: [design] });
      }
      if (path === "/api/control-plane/designs/design-1") {
        return response({ ok: true, design: refreshedDesign });
      }
      if (path.endsWith("/proposals/proposal-1")) {
        return response({ ok: true, proposal });
      }
      if (path.endsWith("/apply")) {
        applyBody = JSON.parse(String(init?.body));
        return response(
          { ok: false, code: "stale_digest", error: "stale" },
          409,
        );
      }
      throw new Error(`Unexpected request: ${path}`);
    });
    render(<InterviewPageContent interviewId="interview-1" />);

    await screen.findByText(proposal.digest);
    fireEvent.change(screen.getByLabelText("적용 대상"), {
      target: { value: "design-1" },
    });
    const confirmation = screen.getByRole("checkbox", {
      name: /제안 aaaaaaaaaaaa/,
    });
    fireEvent.click(confirmation);
    fireEvent.click(screen.getByRole("button", { name: "디자인 등록" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "대상 디자인이 검토 후 변경되었습니다",
    );
    expect(applyBody).toMatchObject({
      expected_revision: 3,
      proposal_id: "proposal-1",
      expected_proposal_digest: proposal.digest,
      design_id: "design-1",
      expected_design_digest: design.digest,
    });
    expect(screen.getByText(proposal.digest)).toBeInTheDocument();
    expect(confirmation).not.toBeChecked();
    expect(confirmation).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "대상 디자인 다시 불러오기" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "디자인 등록" }),
    ).toBeDisabled();

    fireEvent.click(
      screen.getByRole("button", { name: "대상 디자인 다시 불러오기" }),
    );
    expect(await screen.findByText(refreshedDesign.digest)).toBeInTheDocument();
    expect(confirmation).not.toBeChecked();
    expect(confirmation).toBeEnabled();
  });

  test("retains private draft, pending operation, proposal, and storage when only the apply target is missing", async () => {
    const completed = {
      ...session,
      revision: 3,
      status: "completed" as const,
      proposals: [proposalSummary],
    };
    const pendingAnswer = {
      request_id: "11111111-1111-4111-8111-111111111111",
      expected_revision: 3,
      answer: "민감한 미전송 초안",
    };
    window.sessionStorage.setItem(
      "hf-interview-composer:interview-1",
      pendingAnswer.answer,
    );
    window.sessionStorage.setItem(
      "hf-interview-answer:interview-1",
      JSON.stringify(pendingAnswer),
    );
    installFetch((path) => {
      if (path === "/api/control-plane/interviews/interview-1") {
        return response({ ok: true, session: completed });
      }
      if (path === "/api/control-plane/designs") {
        return response({ ok: true, items: [design] });
      }
      if (path.endsWith("/proposals/proposal-1")) {
        return response({ ok: true, proposal });
      }
      if (path.endsWith("/apply")) {
        return response(
          {
            ok: false,
            code: "target_design_not_found",
            error: "target design not found",
          },
          404,
        );
      }
      throw new Error(`Unexpected request: ${path}`);
    });

    render(<InterviewPageContent interviewId="interview-1" />);

    const composer = await screen.findByLabelText("답변");
    expect(composer).toHaveValue(pendingAnswer.answer);
    fireEvent.change(screen.getByLabelText("적용 대상"), {
      target: { value: "design-1" },
    });
    const confirmation = screen.getByRole("checkbox", {
      name: /제안 aaaaaaaaaaaa/,
    });
    fireEvent.click(confirmation);
    fireEvent.click(screen.getByRole("button", { name: "디자인 등록" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "적용 대상 디자인을 찾을 수 없습니다",
    );
    expect(composer).toHaveValue(pendingAnswer.answer);
    expect(screen.getByText(proposal.digest)).toBeInTheDocument();
    expect(screen.getByLabelText("적용 대상")).toHaveValue("new");
    expect(confirmation).not.toBeChecked();
    expect(window.sessionStorage.getItem("hf-interview-composer:interview-1")).toBe(
      pendingAnswer.answer,
    );
    expect(window.sessionStorage.getItem("hf-interview-answer:interview-1")).toBe(
      JSON.stringify(pendingAnswer),
    );
    expect(window.sessionStorage.getItem("hf-interview-selected-proposal:interview-1")).toBe(
      proposal.id,
    );
  });

  test("clears this interview storage when the interview GET itself returns 404", async () => {
    window.sessionStorage.setItem("hf-interview-composer:interview-1", "민감한 초안");
    window.sessionStorage.setItem(
      "hf-interview-answer:interview-1",
      JSON.stringify({
        request_id: "11111111-1111-4111-8111-111111111111",
        expected_revision: 3,
        answer: "민감한 초안",
      }),
    );
    window.sessionStorage.setItem(
      "hf-interview-selected-proposal:interview-1",
      proposal.id,
    );
    installFetch((path) => {
      if (path === "/api/control-plane/interviews/interview-1") {
        return response({ detail: "interview not found" }, 404);
      }
      if (path === "/api/control-plane/designs") {
        return response({ ok: true, items: [] });
      }
      throw new Error(`Unexpected request: ${path}`);
    });

    render(<InterviewPageContent interviewId="interview-1" />);

    expect(
      await screen.findByText(/인터뷰가 만료되었거나 삭제되었습니다/),
    ).toBeInTheDocument();
    expect(window.sessionStorage.getItem("hf-interview-composer:interview-1")).toBeNull();
    expect(window.sessionStorage.getItem("hf-interview-answer:interview-1")).toBeNull();
    expect(window.sessionStorage.getItem("hf-interview-selected-proposal:interview-1")).toBeNull();
  });

  test("clears only this interview storage and sensitive state on terminal 404", async () => {
    const completed = {
      ...session,
      revision: 3,
      status: "completed" as const,
      proposals: [proposalSummary],
    };
    window.sessionStorage.setItem("hf-interview-composer:interview-1", "민감한 초안");
    window.sessionStorage.setItem(
      "hf-interview-answer:interview-1",
      JSON.stringify({
        request_id: "11111111-1111-4111-8111-111111111111",
        expected_revision: 3,
        answer: "민감한 초안",
      }),
    );
    window.sessionStorage.setItem("hf-interview-composer:interview-2", "다른 세션");
    installFetch((path) => {
      if (path === "/api/control-plane/interviews/interview-1") {
        return response({ ok: true, session: completed });
      }
      if (path === "/api/control-plane/designs") {
        return response({ ok: true, items: [] });
      }
      if (path.endsWith("/proposals/proposal-1")) {
        return response({ ok: true, proposal });
      }
      if (path.endsWith("/proposals")) {
        return response({ detail: "interview not found" }, 404);
      }
      throw new Error(`Unexpected request: ${path}`);
    });
    render(<InterviewPageContent interviewId="interview-1" />);

    await screen.findByText(proposal.digest);
    fireEvent.click(screen.getByRole("button", { name: "디자인 제안 생성" }));

    expect(
      await screen.findByText(/인터뷰가 만료되었거나 삭제되었습니다/),
    ).toBeInTheDocument();
    expect(screen.queryByText("어디에서 작업이 가장 오래 멈추나요?")).not.toBeInTheDocument();
    expect(screen.queryByText(proposal.digest)).not.toBeInTheDocument();
    expect(window.sessionStorage.getItem("hf-interview-composer:interview-1")).toBeNull();
    expect(window.sessionStorage.getItem("hf-interview-answer:interview-1")).toBeNull();
    expect(window.sessionStorage.getItem("hf-interview-proposal:interview-1")).toBeNull();
    expect(window.sessionStorage.getItem("hf-interview-composer:interview-2")).toBe(
      "다른 세션",
    );
  });

  test("uses DELETE and clears session storage after explicit deletion", async () => {
    const navigate = vi.fn();
    let deleteMethod: string | undefined;
    installFetch((path, init) => {
      if (
        path === "/api/control-plane/interviews/interview-1" &&
        init?.method === "DELETE"
      ) {
        deleteMethod = init.method;
        return response({ ok: true, deleted: true });
      }
      if (path === "/api/control-plane/interviews/interview-1") {
        return response({ ok: true, session });
      }
      if (path === "/api/control-plane/designs") {
        return response({ ok: true, items: [] });
      }
      throw new Error(`Unexpected request: ${path}`);
    });
    window.sessionStorage.setItem("hf-interview-composer:interview-1", "draft");
    render(
      <InterviewPageContent interviewId="interview-1" navigate={navigate} />,
    );
    await screen.findByText("어디에서 작업이 가장 오래 멈추나요?");

    fireEvent.click(screen.getByRole("button", { name: "삭제" }));
    fireEvent.click(screen.getByRole("button", { name: "인터뷰 영구 삭제" }));

    await waitFor(() => expect(navigate).toHaveBeenCalledWith("/studio"));
    expect(deleteMethod).toBe("DELETE");
    expect(window.sessionStorage.getItem("hf-interview-composer:interview-1")).toBeNull();
  });
});
