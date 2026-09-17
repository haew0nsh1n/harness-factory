import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { StudioDesignPageContent } from "@/components/StudioDesignPageContent";
import profileExample from "../../../../../examples/github-issue/profile.json";
import scenariosExample from "../../../../../examples/github-issue/scenarios.json";
import workflowExample from "../../../../../examples/github-issue/workflow.json";
import catalogExample from "../../../../../catalog/catalog.json";

function jsonResponse(body: object): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

function openTab(name: string) {
  fireEvent.click(screen.getByRole("tab", { name }));
}

function designFixture(status: "draft" | "validated" | "approved" | "build-queued" | "built" | "failed") {
  return {
    id: "design-1",
    organization_id: "org-acme",
    customer_id: "cust-1",
    name: `Design ${status}`,
    language: "ko",
    profile: {
      ...profileExample,
      sdlc: profileExample.sdlc.slice(0, 1),
      glossary: { brief: profileExample.glossary.brief },
      systems: profileExample.systems.slice(0, 1).map((system) => ({
        ...system,
        extension: "preserve-system",
      })),
      roles: profileExample.roles.slice(0, 1),
      pains: profileExample.pains.slice(0, 1),
      success_criteria: profileExample.success_criteria.slice(0, 1),
      constraints: profileExample.constraints.slice(0, 1),
      facts: profileExample.facts.slice(0, 1),
      assumptions: profileExample.assumptions.slice(0, 1),
      unknowns: profileExample.unknowns.slice(0, 1),
      extension: { preserve: "profile" },
    },
    workflow: {
      ...workflowExample,
      inputs: workflowExample.inputs.slice(0, 1),
      outputs: workflowExample.outputs.slice(0, 1),
      customer_rules: workflowExample.customer_rules.slice(0, 1),
      steps: workflowExample.steps.slice(0, 1).map((step) => ({
        ...step,
        extension: "preserve-step",
      })),
      traceability: workflowExample.traceability.slice(0, 1),
      extension: { preserve: "workflow" },
    },
    scenarios: {
      ...scenariosExample,
      scenarios: scenariosExample.scenarios.slice(0, 1).map((scenario) => ({
        ...scenario,
        extension: "preserve-scenario",
      })),
      extension: { preserve: "scenarios" },
    },
    catalog: catalogExample,
    revision: 3,
    digest: "a".repeat(64),
    status,
    validation_findings: [
      {
        field: "workflow",
        code: "invalid-design",
        message: "workflow finding text only",
      },
    ],
    created_by: "author-1",
    created_at: "2026-09-14T00:00:00Z",
    updated_at: "2026-09-14T00:00:00Z",
  };
}

describe("StudioDesignPageContent", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  test.each([
    ["draft", false, true, true],
    ["validated", true, false, true],
    ["approved", true, true, false],
    ["built", true, true, true],
  ] as const)(
    "enables lifecycle buttons from %s status",
    async (status, validateDisabled, approveDisabled, queueDisabled) => {
      vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse({ ok: true, design: designFixture(status) }));

      render(<StudioDesignPageContent designId="design-1" />);

      expect(await screen.findByRole("heading", { name: `Design ${status}` })).toBeInTheDocument();
      const validateButton = screen.getByRole("button", { name: "디자인 검증" });
      const approveButton = screen.getByRole("button", { name: "다이제스트 승인" });
      const rejectButton = screen.getByRole("button", { name: "검토 반려" });
      const queueButton = screen.getByRole("button", { name: "빌드 요청" });

      if (validateDisabled) {
        expect(validateButton).toBeDisabled();
      } else {
        expect(validateButton).toBeEnabled();
      }

      if (approveDisabled) {
        expect(approveButton).toBeDisabled();
        expect(rejectButton).toBeDisabled();
      } else {
        expect(approveButton).toBeEnabled();
        expect(rejectButton).toBeEnabled();
      }

      if (queueDisabled) {
        expect(queueButton).toBeDisabled();
      } else {
        expect(queueButton).toBeEnabled();
      }

      expect(screen.getByRole("button", { name: "초안 저장" })).toBeEnabled();
    },
  );

  test("renders registry registration only for a built design without changing lifecycle actions", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        jsonResponse({ ok: true, design: designFixture("built") }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          ok: true,
          actor: {
            organization_id: "org-acme",
            subject_id: "author-1",
            roles: ["author", "reviewer", "registry-admin"],
          },
        }),
      )
      .mockResolvedValueOnce(jsonResponse({ ok: true, items: [] }));

    render(<StudioDesignPageContent designId="design-1" />);

    await screen.findByRole("heading", { name: "Design built" });
    openTab("레지스트리 등록");
    expect(
      await screen.findByRole("heading", { name: "레지스트리 등록" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "디자인 검증" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "다이제스트 승인" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "빌드 요청" })).toBeDisabled();
  });

  test("shows field-specific parse validation and prevents submission", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse({ ok: true, design: designFixture("draft") }));

    render(<StudioDesignPageContent designId="design-1" />);

    await screen.findByRole("heading", { name: "Design draft" });
    openTab("고급");
    fireEvent.click(screen.getByText("디버그 JSON"));
    fireEvent.change(screen.getByLabelText("워크플로우 JSON"), {
      target: { value: "{bad-workflow" },
    });
    fireEvent.click(screen.getByText("디버그 JSON"));
    fireEvent.click(screen.getByRole("button", { name: "초안 저장" }));

    expect(
      (await screen.findAllByText(/워크플로우 JSON이 올바르지 않습니다:/i)).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getByRole("button", { name: "디버그 JSON 열고 수정" }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "디버그 JSON 열고 수정" }));
    await waitFor(() =>
      expect(screen.getByRole("textbox", { name: "워크플로우 JSON" })).toHaveFocus(),
    );
    expect(fetchSpy).toHaveBeenCalledTimes(1);
  });

  test("keeps debug JSON closed by default and preserves invalid text across keyboard toggles", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      jsonResponse({ ok: true, design: designFixture("draft") }),
    );

    render(<StudioDesignPageContent designId="design-1" />);

    await screen.findByRole("heading", { name: "Design draft" });
    openTab("고급");
    expect(
      screen.getByRole("textbox", { name: "워크플로우 JSON" }),
    ).not.toBeVisible();

    const summary = screen.getByText("디버그 JSON");
    summary.focus();
    fireEvent.keyDown(summary, { key: "Enter" });
    fireEvent.click(summary);
    const workflowJson = screen.getByRole("textbox", { name: "워크플로우 JSON" });
    fireEvent.change(workflowJson, { target: { value: "{still-invalid" } });
    fireEvent.click(summary);
    expect(
      screen.getByRole("textbox", { name: "워크플로우 JSON" }),
    ).not.toBeVisible();

    summary.focus();
    fireEvent.keyDown(summary, { key: " " });
    fireEvent.click(summary);
    expect(screen.getByRole("textbox", { name: "워크플로우 JSON" })).toHaveValue(
      "{still-invalid",
    );
  });

  test("keeps a new hidden syntax error actionable after a prior save error is cleared", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse({ ok: true, design: designFixture("draft") }));

    render(<StudioDesignPageContent designId="design-1" />);

    await screen.findByRole("heading", { name: "Design draft" });
    openTab("고급");
    fireEvent.click(screen.getByText("디버그 JSON"));
    const workflowJson = screen.getByRole("textbox", { name: "워크플로우 JSON" });
    fireEvent.change(workflowJson, { target: { value: "{first-invalid" } });
    fireEvent.click(screen.getByRole("button", { name: "초안 저장" }));
    expect(
      (await screen.findAllByText(/워크플로우 JSON이 올바르지 않습니다:/i)).length,
    ).toBeGreaterThan(0);

    fireEvent.change(workflowJson, { target: { value: "{second-invalid" } });
    fireEvent.click(screen.getByText("디버그 JSON"));

    expect(
      screen.getByRole("button", { name: "디버그 JSON 열고 수정" }),
    ).toBeVisible();
    expect(screen.getByRole("textbox", { name: "워크플로우 JSON" })).not.toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "디버그 JSON 열고 수정" }));
    await waitFor(() => expect(workflowJson).toHaveFocus());
    expect(workflowJson).toHaveValue("{second-invalid");
    expect(fetchSpy).toHaveBeenCalledTimes(1);
  });

  test("saves modified canonical JSON documents", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    fetchSpy
      .mockResolvedValueOnce(jsonResponse({ ok: true, design: designFixture("draft") }))
      .mockResolvedValueOnce(
        jsonResponse({
          ok: true,
          design: {
            ...designFixture("draft"),
            profile: { ...profileExample, name: "updated-profile" },
            revision: 4,
          },
        }),
      );

    render(<StudioDesignPageContent designId="design-1" />);

    await screen.findByRole("heading", { name: "Design draft" });
    openTab("고급");
    fireEvent.click(screen.getByText("디버그 JSON"));
    fireEvent.change(screen.getByLabelText("프로필 JSON"), {
      target: {
        value: JSON.stringify(
          { ...profileExample, name: "updated-profile" },
          null,
          2,
        ),
      },
    });
    fireEvent.click(screen.getByRole("button", { name: "초안 저장" }));

    await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(2));
    const [, options] = fetchSpy.mock.calls[1] ?? [];
    expect(options).toMatchObject({ method: "PUT" });
    expect(JSON.parse(String(options?.body))).toMatchObject({
      customer_id: "cust-1",
      name: "Design draft",
      profile: { name: "updated-profile" },
    });
  });

  test("keeps a form name edit when advanced JSON changes an unrelated constraint", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    fetchSpy
      .mockResolvedValueOnce(jsonResponse({ ok: true, design: designFixture("draft") }))
      .mockResolvedValueOnce(
        jsonResponse({
          ok: true,
          design: {
            ...designFixture("draft"),
            profile: {
              ...profileExample,
              name: "Form-edited team",
              constraints: ["Updated in advanced JSON"],
              extension: { preserve: "profile" },
            },
            revision: 4,
          },
        }),
      );

    render(<StudioDesignPageContent designId="design-1" />);

    await screen.findByRole("heading", { name: "Design draft" });
    fireEvent.change(screen.getByLabelText("고객 이름"), {
      target: { value: "Form-edited team" },
    });
    openTab("고급");
    fireEvent.click(screen.getByText("디버그 JSON"));
    const profileJson = screen.getByLabelText("프로필 JSON");
    const advanced = JSON.parse((profileJson as HTMLTextAreaElement).value);
    advanced.constraints = ["Updated in advanced JSON"];
    fireEvent.change(profileJson, {
      target: { value: JSON.stringify(advanced, null, 2) },
    });
    fireEvent.click(screen.getByRole("button", { name: "초안 저장" }));

    await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(2));
    const body = JSON.parse(String(fetchSpy.mock.calls[1]?.[1]?.body));
    expect(body.profile.name).toBe("Form-edited team");
    expect(body.profile.constraints).toEqual(["Updated in advanced JSON"]);
    expect(body.profile.extension).toEqual({ preserve: "profile" });
  });

  test("keeps transient structured rows and dirty state while invalid raw JSON is repaired", async () => {
    const loaded = {
      ...designFixture("draft"),
      profile: {
        ...designFixture("draft").profile,
        glossary: {
          brief: "Original brief definition",
          handoff: "Original handoff definition",
        },
      },
    };
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      jsonResponse({ ok: true, design: loaded }),
    );

    render(<StudioDesignPageContent designId="design-1" />);

    await screen.findByRole("heading", { name: "Design draft" });
    const pendingTerm = screen.getByLabelText("용어 1 키");
    fireEvent.change(pendingTerm, { target: { value: "handoff" } });
    expect(screen.getByText(/이미 존재하는 용어입니다/)).toBeInTheDocument();

    openTab("고급");
    fireEvent.click(screen.getByText("디버그 JSON"));
    const workflowJson = screen.getByLabelText("워크플로우 JSON");
    const originalWorkflow = (workflowJson as HTMLTextAreaElement).value;
    fireEvent.change(workflowJson, { target: { value: "{invalid" } });
    expect(screen.getByText(/구조화된 양식을 갱신할 수 없는 JSON 형식/)).toBeInTheDocument();
    fireEvent.change(workflowJson, { target: { value: originalWorkflow } });

    openTab("프로필");
    expect(screen.getByLabelText("용어 1 키")).toHaveValue("handoff");
    expect(screen.getByText(/이미 존재하는 용어입니다/)).toBeInTheDocument();
    const event = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);
  });

  test("blocks PUT for an invalid typed field and preserves it across a sibling edit", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse({ ok: true, design: designFixture("draft") }));

    render(<StudioDesignPageContent designId="design-1" />);

    await screen.findByRole("heading", { name: "Design draft" });
    fireEvent.change(screen.getByLabelText("고객 ID"), {
      target: { value: "Not Valid" },
    });
    fireEvent.change(screen.getByLabelText("고객 이름"), {
      target: { value: "Sibling edit" },
    });

    expect(screen.getByLabelText("고객 ID")).toHaveValue("Not Valid");
    expect(screen.getByText(/소문자 하이픈 식별자/)).toBeInTheDocument();
    const event = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: "초안 저장" }));
    expect(await screen.findByText(/양식 오류를 수정한 뒤 저장하세요/)).toBeInTheDocument();
    expect(fetchSpy).toHaveBeenCalledTimes(1);
  });

  test("preserves an invalid string-list entry by original index during a sibling edit", async () => {
    const invalidRole = { extension: "retain-original-object" };
    const loaded = {
      ...designFixture("draft"),
      profile: {
        ...designFixture("draft").profile,
        roles: ["author", invalidRole],
      },
    };
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse({ ok: true, design: loaded }));

    render(<StudioDesignPageContent designId="design-1" />);

    await screen.findByRole("heading", { name: "Design draft" });
    fireEvent.change(screen.getByLabelText("역할 1"), {
      target: { value: "reviewer" },
    });

    openTab("고급");
    fireEvent.click(screen.getByText("디버그 JSON"));
    const profile = JSON.parse(
      (screen.getByLabelText("프로필 JSON") as HTMLTextAreaElement).value,
    );
    expect(profile.roles).toEqual(["reviewer", invalidRole]);
    openTab("프로필");
    expect(screen.getByText(/모든 항목은 문자열이어야 합니다/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "초안 저장" }));
    expect(await screen.findByText(/양식 오류를 수정한 뒤 저장하세요/)).toBeInTheDocument();
    expect(fetchSpy).toHaveBeenCalledTimes(1);
  });

  test("preserves an invalid object-list entry by original index during a sibling edit", async () => {
    const invalidPain = "retain-original-invalid-entry";
    const loaded = {
      ...designFixture("draft"),
      profile: {
        ...designFixture("draft").profile,
        pains: [designFixture("draft").profile.pains[0], invalidPain],
      },
    };
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse({ ok: true, design: loaded }));

    render(<StudioDesignPageContent designId="design-1" />);

    await screen.findByRole("heading", { name: "Design draft" });
    fireEvent.change(screen.getByLabelText("문제 1 설명"), {
      target: { value: "Edited valid sibling" },
    });

    openTab("고급");
    fireEvent.click(screen.getByText("디버그 JSON"));
    const profile = JSON.parse(
      (screen.getByLabelText("프로필 JSON") as HTMLTextAreaElement).value,
    );
    expect(profile.pains[0].description).toBe("Edited valid sibling");
    expect(profile.pains[1]).toBe(invalidPain);
    openTab("프로필");
    expect(screen.getByText(/현재 값은 객체 목록이어야 합니다/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "초안 저장" }));
    expect(await screen.findByText(/양식 오류를 수정한 뒤 저장하세요/)).toBeInTheDocument();
    expect(fetchSpy).toHaveBeenCalledTimes(1);
  });

  test("keeps glossary focus while typing and blocks duplicate-key overwrite", async () => {
    const loaded = {
      ...designFixture("draft"),
      profile: {
        ...designFixture("draft").profile,
        glossary: {
          brief: "Original brief definition",
          handoff: "Original handoff definition",
        },
      },
    };
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse({ ok: true, design: loaded }));

    render(<StudioDesignPageContent designId="design-1" />);

    await screen.findByRole("heading", { name: "Design draft" });
    const termInput = screen.getByLabelText("용어 1 키");
    termInput.focus();
    for (const value of ["h", "ha", "han", "hand", "hando", "handoff"]) {
      fireEvent.change(termInput, { target: { value } });
      expect(document.activeElement).toBe(termInput);
    }

    expect(screen.getByText(/이미 존재하는 용어입니다/)).toBeInTheDocument();
    const event = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: "초안 저장" }));
    expect(await screen.findByText(/양식 오류를 수정한 뒤 저장하세요/)).toBeInTheDocument();
    expect(fetchSpy).toHaveBeenCalledTimes(1);

    openTab("고급");
    fireEvent.click(screen.getByText("디버그 JSON"));
    const profile = JSON.parse(
      (screen.getByLabelText("프로필 JSON") as HTMLTextAreaElement).value,
    );
    expect(profile.glossary).toEqual({
      brief: "Original brief definition",
      handoff: "Original handoff definition",
    });
  });

  test("blocks two pending glossary renames from swapping occupied canonical keys", async () => {
    const loaded = {
      ...designFixture("draft"),
      profile: {
        ...designFixture("draft").profile,
        glossary: {
          brief: "Original brief definition",
          handoff: "Original handoff definition",
        },
      },
    };
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse({ ok: true, design: loaded }));

    render(<StudioDesignPageContent designId="design-1" />);

    await screen.findByRole("heading", { name: "Design draft" });
    const firstTerm = screen.getByLabelText("용어 1 키");
    const secondTerm = screen.getByLabelText("용어 2 키");
    firstTerm.focus();
    fireEvent.change(firstTerm, { target: { value: "handoff" } });
    expect(document.activeElement).toBe(firstTerm);
    secondTerm.focus();
    fireEvent.change(secondTerm, { target: { value: "brief" } });
    expect(document.activeElement).toBe(secondTerm);
    fireEvent.blur(secondTerm);

    expect(screen.getAllByText(/이미 존재하는 용어입니다/)).toHaveLength(2);
    fireEvent.click(screen.getByRole("button", { name: "초안 저장" }));
    expect(await screen.findByText(/양식 오류를 수정한 뒤 저장하세요/)).toBeInTheDocument();
    expect(fetchSpy).toHaveBeenCalledTimes(1);

    openTab("고급");
    fireEvent.click(screen.getByText("디버그 JSON"));
    const profile = JSON.parse(
      (screen.getByLabelText("프로필 JSON") as HTMLTextAreaElement).value,
    );
    expect(profile.glossary).toEqual({
      brief: "Original brief definition",
      handoff: "Original handoff definition",
    });
  });

  test("commits a resolved glossary rename and saves both definitions", async () => {
    const loaded = {
      ...designFixture("draft"),
      profile: {
        ...designFixture("draft").profile,
        glossary: {
          brief: "Original brief definition",
          handoff: "Original handoff definition",
        },
      },
    };
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    fetchSpy
      .mockResolvedValueOnce(jsonResponse({ ok: true, design: loaded }))
      .mockResolvedValueOnce(
        jsonResponse({
          ok: true,
          design: {
            ...loaded,
            profile: {
              ...loaded.profile,
              glossary: {
                summary: "Original brief definition",
                handoff: "Original handoff definition",
              },
            },
            revision: 4,
          },
        }),
      );

    render(<StudioDesignPageContent designId="design-1" />);

    await screen.findByRole("heading", { name: "Design draft" });
    const termInput = screen.getByLabelText("용어 1 키");
    termInput.focus();
    for (const value of ["s", "su", "sum", "summ", "summa", "summar", "summary"]) {
      fireEvent.change(termInput, { target: { value } });
      expect(document.activeElement).toBe(termInput);
    }
    fireEvent.blur(termInput);

    openTab("고급");
    fireEvent.click(screen.getByText("디버그 JSON"));
    await waitFor(() => {
      const profile = JSON.parse(
        (screen.getByLabelText("프로필 JSON") as HTMLTextAreaElement).value,
      );
      expect(profile.glossary).toEqual({
        summary: "Original brief definition",
        handoff: "Original handoff definition",
      });
    });
    fireEvent.click(screen.getByRole("button", { name: "초안 저장" }));

    await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(2));
    const body = JSON.parse(String(fetchSpy.mock.calls[1]?.[1]?.body));
    expect(body.profile.glossary).toEqual({
      summary: "Original brief definition",
      handoff: "Original handoff definition",
    });
  });

  test("typed nested controls update canonical fields and preserve unknown nested fields", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    fetchSpy
      .mockResolvedValueOnce(jsonResponse({ ok: true, design: designFixture("draft") }))
      .mockResolvedValueOnce(jsonResponse({ ok: true, design: designFixture("draft") }));

    render(<StudioDesignPageContent designId="design-1" />);

    await screen.findByRole("heading", { name: "Design draft" });
    fireEvent.change(screen.getByLabelText("이슈 트래커 제공자"), {
      target: { value: "jira" },
    });
    fireEvent.change(screen.getByLabelText("이슈 트래커 프로젝트"), {
      target: { value: "TEAM" },
    });
    openTab("워크플로우");
    fireEvent.change(screen.getByLabelText("clarify 단계 승인 시점"), {
      target: { value: "before" },
    });
    openTab("시나리오");
    fireEvent.change(screen.getByLabelText("normal-handoff 시나리오 예상 상태"), {
      target: { value: "completed" },
    });
    fireEvent.click(screen.getByRole("button", { name: "초안 저장" }));

    await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(2));
    const body = JSON.parse(String(fetchSpy.mock.calls[1]?.[1]?.body));
    expect(body.profile.issue_tracker.provider).toBe("jira");
    expect(body.workflow.steps[0].approval_timing).toBe("before");
    expect(body.scenarios.scenarios[0].expect).toBe("completed");
    expect(body.profile.extension).toEqual({ preserve: "profile" });
    expect(body.profile.systems[0].extension).toBe("preserve-system");
    expect(body.workflow.extension).toEqual({ preserve: "workflow" });
    expect(body.workflow.steps[0].extension).toBe("preserve-step");
    expect(body.scenarios.extension).toEqual({ preserve: "scenarios" });
    expect(body.scenarios.scenarios[0].extension).toBe("preserve-scenario");
  });

  test("validates a draft through the real design endpoint", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    fetchSpy
      .mockResolvedValueOnce(jsonResponse({ ok: true, design: designFixture("draft") }))
      .mockResolvedValueOnce(
        jsonResponse({ ok: true, design: designFixture("validated") }),
      );

    render(<StudioDesignPageContent designId="design-1" />);

    await screen.findByRole("heading", { name: "Design draft" });
    fireEvent.click(screen.getByRole("button", { name: "디자인 검증" }));

    await screen.findByText("검증됨");
    expect(fetchSpy).toHaveBeenNthCalledWith(
      2,
      "/api/control-plane/designs/design-1/validate",
      expect.objectContaining({ method: "POST" }),
    );
  });

  test("submits approval against the exact current digest", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    fetchSpy
      .mockResolvedValueOnce(
        jsonResponse({ ok: true, design: designFixture("validated") }),
      )
      .mockResolvedValueOnce(
        jsonResponse({ ok: true, design: designFixture("approved") }),
      );

    render(<StudioDesignPageContent designId="design-1" />);

    await screen.findByRole("heading", { name: "Design validated" });
    fireEvent.click(screen.getByRole("button", { name: "다이제스트 승인" }));

    await screen.findByText("승인됨");
    const [, options] = fetchSpy.mock.calls[1] ?? [];
    expect(options).toMatchObject({ method: "POST" });
    expect(JSON.parse(String(options?.body))).toEqual({
      expected_digest: "a".repeat(64),
      decision: "approved",
    });
  });

  test("exposes stale revision conflicts without hiding server detail", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse({ ok: true, design: designFixture("draft") }))
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            ok: false,
            code: "revision_conflict",
            error: "expected revision 3 but found 4",
          }),
          { status: 409, headers: { "content-type": "application/json" } },
        ),
      );

    render(<StudioDesignPageContent designId="design-1" />);

    await screen.findByRole("heading", { name: "Design draft" });
    fireEvent.click(screen.getByRole("button", { name: "초안 저장" }));

    expect(
      await screen.findByText(
        /최신 리비전과 충돌했습니다.*expected revision 3 but found 4/,
      ),
    ).toBeInTheDocument();
  });

  test("refetches design after queueing a build so lifecycle actions update", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    fetchSpy
      .mockResolvedValueOnce(jsonResponse({ ok: true, design: designFixture("approved") }))
      .mockResolvedValueOnce(
        jsonResponse({
          ok: true,
          build: {
            id: "build-1",
            organization_id: "org-acme",
            design_id: "design-1",
            design_digest: "a".repeat(64),
            status: "queued",
            attempts: 1,
            artifact_key: null,
            artifact_digest: null,
            error_code: null,
            created_at: "2026-09-14T00:00:00Z",
            started_at: null,
            finished_at: null,
            updated_at: "2026-09-14T00:00:00Z",
          },
        }),
      )
      .mockResolvedValueOnce(jsonResponse({ ok: true, design: designFixture("build-queued") }));

    render(<StudioDesignPageContent designId="design-1" />);

    await screen.findByRole("heading", { name: "Design approved" });
    fireEvent.click(screen.getByRole("button", { name: "빌드 요청" }));

    expect(await screen.findByText("빌드 대기")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "디자인 검증" })).toBeDisabled();
      expect(screen.getByRole("button", { name: "다이제스트 승인" })).toBeDisabled();
    });
    const [, options] = fetchSpy.mock.calls[1] ?? [];
    expect(JSON.parse(String(options?.body))).toEqual({
      expected_digest: "a".repeat(64),
    });
  });

  test("preserves successful queued build state when design refresh fails", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    fetchSpy
      .mockResolvedValueOnce(jsonResponse({ ok: true, design: designFixture("approved") }))
      .mockResolvedValueOnce(
        jsonResponse({
          ok: true,
          build: {
            id: "build-1",
            organization_id: "org-acme",
            design_id: "design-1",
            design_digest: "a".repeat(64),
            status: "queued",
            attempts: 1,
            artifact_key: null,
            artifact_digest: null,
            error_code: null,
            created_at: "2026-09-14T00:00:00Z",
            started_at: null,
            finished_at: null,
            updated_at: "2026-09-14T00:00:00Z",
          },
        }),
      )
      .mockRejectedValueOnce(new Error("refresh failed"));

    render(<StudioDesignPageContent designId="design-1" />);

    await screen.findByRole("heading", { name: "Design approved" });
    fireEvent.click(screen.getByRole("button", { name: "빌드 요청" }));

    expect(await screen.findByText("빌드 대기")).toBeInTheDocument();
    expect(
      await screen.findByText("빌드를 요청했지만 최신 디자인 상태를 불러오지 못했습니다."),
    ).toBeInTheDocument();
    expect(screen.queryByText("빌드를 요청하지 못했습니다.")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "빌드 요청" })).toBeDisabled();
  });
  test("shows current server findings when validation fails", async () => {
    const failedDesign = {
      ...designFixture("draft"),
      validation_findings: [
        {
          field: "contract",
          code: "invalid-design",
          message: "validation: workflow: step clarify is not in the catalog",
        },
      ],
    };
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    fetchSpy
      .mockResolvedValueOnce(
        jsonResponse({
          ok: true,
          design: { ...designFixture("draft"), validation_findings: null },
        }),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            ok: false,
            error: "design validation failed",
            code: "invalid_design",
            finding: failedDesign.validation_findings[0],
            design: failedDesign,
          }),
          { status: 422, headers: { "content-type": "application/json" } },
        ),
      );

    render(<StudioDesignPageContent designId="design-1" />);

    await screen.findByRole("heading", { name: "Design draft" });
    fireEvent.click(screen.getByRole("button", { name: "디자인 검증" }));
    openTab("빌드");

    expect(
      await screen.findByText(
        /contract: invalid-design: validation: workflow: step clarify is not in the catalog/,
      ),
    ).toBeInTheDocument();
    expect(await screen.findByText("design validation failed")).toBeInTheDocument();
    expect(screen.queryByText("검증 결과가 없습니다.")).not.toBeInTheDocument();
  });

  test("falls back to the error finding when no design is returned", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    fetchSpy
      .mockResolvedValueOnce(
        jsonResponse({
          ok: true,
          design: { ...designFixture("draft"), validation_findings: null },
        }),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            ok: false,
            error: "design validation failed",
            code: "invalid_design",
            finding: {
              field: "catalog",
              code: "invalid-design",
              message: "validation: catalog: snapshot does not match server catalog",
            },
          }),
          { status: 422, headers: { "content-type": "application/json" } },
        ),
      );

    render(<StudioDesignPageContent designId="design-1" />);

    await screen.findByRole("heading", { name: "Design draft" });
    fireEvent.click(screen.getByRole("button", { name: "디자인 검증" }));
    openTab("카탈로그");

    expect(
      await screen.findByText(
        /invalid-design: validation: catalog: snapshot does not match server catalog/,
      ),
    ).toBeInTheDocument();
  });

  test("renders findings as plain text only", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    fetchSpy
      .mockResolvedValueOnce(
        jsonResponse({
          ok: true,
          design: { ...designFixture("draft"), validation_findings: null },
        }),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            ok: false,
            error: "design validation failed",
            code: "invalid_design",
            finding: {
              field: "workflow",
              code: "invalid-design",
              message: "<img src=x onerror=\"alert(1)\">",
            },
          }),
          { status: 422, headers: { "content-type": "application/json" } },
        ),
      );

    render(<StudioDesignPageContent designId="design-1" />);

    await screen.findByRole("heading", { name: "Design draft" });
    fireEvent.click(screen.getByRole("button", { name: "디자인 검증" }));
    openTab("워크플로우");

    const finding = await screen.findByText(/onerror=/);
    expect(finding.querySelector("img")).toBeNull();
    expect(finding.textContent).toContain("<img src=x");
  });

  test("shows only persisted profile evidence and an honest interview boundary", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      jsonResponse({
        ok: true,
        design: {
          ...designFixture("draft"),
          profile: {
            facts: [
              {
                id: "fact-review",
                statement: "리뷰 전에 승인 기준을 확인합니다.",
              },
            ],
            assumptions: ["테스트 명령을 실행할 수 있다고 가정합니다."],
            unknowns: ["저장소 접근 권한은 아직 확인되지 않았습니다."],
          },
        },
      }),
    );

    render(<StudioDesignPageContent designId="design-1" />);

    await screen.findByRole("heading", { name: "Design draft" });
    openTab("근거");
    expect(
      await screen.findByRole("heading", {
        name: "대화형 인터뷰는 아직 제공되지 않습니다.",
      }),
    ).toBeInTheDocument();
    expect(screen.getAllByText("리뷰 전에 승인 기준을 확인합니다.").length).toBeGreaterThan(0);
    expect(
      screen.getAllByText("테스트 명령을 실행할 수 있다고 가정합니다.").length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText("저장소 접근 권한은 아직 확인되지 않았습니다.").length,
    ).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: "사실 확인" })).not.toBeInTheDocument();
    expect(screen.getByText("답변 입력 미제공")).toBeInTheDocument();
  });

  test("shows a catalog summary without exposing raw catalog JSON by default", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      jsonResponse({ ok: true, design: designFixture("draft") }),
    );

    render(<StudioDesignPageContent designId="design-1" />);

    await screen.findByRole("heading", { name: "Design draft" });
    openTab("카탈로그");
    expect(screen.getByRole("heading", { name: "승인 카탈로그" })).toBeInTheDocument();
    expect(screen.getByText(/6개 스킬/)).toBeInTheDocument();
    expect(
      screen.queryByRole("textbox", { name: "카탈로그 JSON" }),
    ).not.toBeInTheDocument();
  });
});
