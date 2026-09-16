import { fireEvent, render, screen, waitFor } from "@testing-library/react";

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
      "워크플로 범위가 아직 선택되지 않았습니다.",
    );
    expect(screen.getByRole("alert")).not.toHaveTextContent(
      "workflow scope has not been selected",
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
      screen.getByRole("button", { name: "정확한 제안 적용" }),
    ).toBeEnabled();

    fireEvent.change(screen.getByLabelText("적용 대상"), {
      target: { value: "design-1" },
    });
    expect(confirmation).not.toBeChecked();
    expect(
      screen.getByRole("button", { name: "정확한 제안 적용" }),
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

    await screen.findByText(/워크플로 범위 release-handoff/);
    expect(confirmation).not.toBeChecked();
    expect(
      screen.getByRole("button", { name: "정확한 제안 적용" }),
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
    fireEvent.click(screen.getByRole("button", { name: "정확한 제안 적용" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "대상 설계가 검토 후 변경되었습니다",
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
      screen.getByRole("button", { name: "대상 설계 다시 불러오기" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "정확한 제안 적용" }),
    ).toBeDisabled();

    fireEvent.click(
      screen.getByRole("button", { name: "대상 설계 다시 불러오기" }),
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
    fireEvent.click(screen.getByRole("button", { name: "정확한 제안 적용" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "적용 대상 설계를 찾을 수 없습니다",
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
    fireEvent.click(screen.getByRole("button", { name: "설계 제안 생성" }));

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

    fireEvent.click(screen.getByRole("button", { name: "삭제 확인" }));
    fireEvent.click(screen.getByRole("button", { name: "인터뷰 영구 삭제" }));

    await waitFor(() => expect(navigate).toHaveBeenCalledWith("/studio"));
    expect(deleteMethod).toBe("DELETE");
    expect(window.sessionStorage.getItem("hf-interview-composer:interview-1")).toBeNull();
  });
});
