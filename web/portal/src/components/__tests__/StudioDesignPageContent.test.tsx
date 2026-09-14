import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { StudioDesignPageContent } from "@/components/StudioDesignPageContent";

function jsonResponse(body: object): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

function designFixture(status: "draft" | "validated" | "approved" | "build-queued" | "built" | "failed") {
  return {
    id: "design-1",
    organization_id: "org-acme",
    customer_id: "cust-1",
    name: `Design ${status}`,
    profile: { name: "profile" },
    workflow: { name: "workflow" },
    scenarios: { items: [] },
    catalog: { tools: [] },
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
    ["built", true, true, false],
  ] as const)(
    "enables lifecycle buttons from %s status",
    async (status, validateDisabled, approveDisabled, queueDisabled) => {
      vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse({ ok: true, design: designFixture(status) }));

      render(<StudioDesignPageContent designId="design-1" />);

      expect(await screen.findByRole("heading", { name: `Design ${status}` })).toBeInTheDocument();
      const validateButton = screen.getByRole("button", { name: "Validate" });
      const approveButton = screen.getByRole("button", { name: "Approve digest" });
      const rejectButton = screen.getByRole("button", { name: "Reject digest" });
      const queueButton = screen.getByRole("button", { name: "Queue build" });

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

      expect(screen.getByRole("button", { name: "Save draft" })).toBeEnabled();
    },
  );

  test("shows field-specific parse validation and prevents submission", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse({ ok: true, design: designFixture("draft") }));

    render(<StudioDesignPageContent designId="design-1" />);

    await screen.findByRole("heading", { name: "Design draft" });
    fireEvent.change(screen.getByLabelText("Workflow JSON"), {
      target: { value: "{bad-workflow" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));

    expect(await screen.findByText(/Workflow JSON is invalid:/i)).toBeInTheDocument();
    expect(fetchSpy).toHaveBeenCalledTimes(1);
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
    fireEvent.click(screen.getByRole("button", { name: "Queue build" }));

    expect(await screen.findByText("build-queued")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Validate" })).toBeDisabled();
      expect(screen.getByRole("button", { name: "Approve digest" })).toBeDisabled();
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
    fireEvent.click(screen.getByRole("button", { name: "Queue build" }));

    expect(await screen.findByText("build-queued")).toBeInTheDocument();
    expect(
      await screen.findByText(/Build queued\. Unable to refresh latest design status\./i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Unable to queue build\./i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Queue build" })).toBeDisabled();
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
    fireEvent.click(screen.getByRole("button", { name: "Validate" }));

    expect(
      await screen.findByText(
        /contract: invalid-design: validation: workflow: step clarify is not in the catalog/,
      ),
    ).toBeInTheDocument();
    expect(await screen.findByText("design validation failed")).toBeInTheDocument();
    expect(screen.queryByText("No validation findings.")).not.toBeInTheDocument();
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
    fireEvent.click(screen.getByRole("button", { name: "Validate" }));

    expect(
      await screen.findByText(
        /catalog: invalid-design: validation: catalog: snapshot does not match server catalog/,
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
    fireEvent.click(screen.getByRole("button", { name: "Validate" }));

    const finding = await screen.findByText(/onerror=/);
    expect(finding.querySelector("img")).toBeNull();
    expect(finding.textContent).toContain("<img src=x");
  });
});
