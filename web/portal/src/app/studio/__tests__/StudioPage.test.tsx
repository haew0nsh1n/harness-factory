"use client";

import { render, screen } from "@testing-library/react";

import { StudioPageContent } from "@/components/StudioPageContent";

function jsonResponse(body: object): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

describe("StudioPageContent", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  test("lists design status and next actions from lifecycle state", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        jsonResponse({
          ok: true,
          items: [
            { id: "design-draft", customer_id: "cust-1", name: "Draft Design", profile: {}, workflow: {}, scenarios: {}, catalog: {}, revision: 1, digest: "a".repeat(64), status: "draft", validation_findings: null, organization_id: "org-acme", created_by: "author-1", created_at: "2026-09-14T00:00:00Z", updated_at: "2026-09-14T00:00:00Z" },
            { id: "design-validated", customer_id: "cust-2", name: "Validated Design", profile: {}, workflow: {}, scenarios: {}, catalog: {}, revision: 4, digest: "b".repeat(64), status: "validated", validation_findings: [], organization_id: "org-acme", created_by: "author-1", created_at: "2026-09-14T00:00:00Z", updated_at: "2026-09-14T00:00:00Z" },
            { id: "design-approved", customer_id: "cust-3", name: "Approved Design", profile: {}, workflow: {}, scenarios: {}, catalog: {}, revision: 2, digest: "c".repeat(64), status: "approved", validation_findings: [], organization_id: "org-acme", created_by: "author-1", created_at: "2026-09-14T00:00:00Z", updated_at: "2026-09-14T00:00:00Z" },
            { id: "design-built", customer_id: "cust-4", name: "Built Design", profile: {}, workflow: {}, scenarios: {}, catalog: {}, revision: 9, digest: "d".repeat(64), status: "built", validation_findings: [], organization_id: "org-acme", created_by: "author-1", created_at: "2026-09-14T00:00:00Z", updated_at: "2026-09-14T00:00:00Z" }
          ],
        }),
      );

    render(<StudioPageContent />);

    expect(await screen.findByText("Draft Design")).toBeInTheDocument();
    expect(screen.getByText("Validated Design")).toBeInTheDocument();
    expect(screen.getByText("Approved Design")).toBeInTheDocument();
    expect(screen.getByText("Built Design")).toBeInTheDocument();

    expect(screen.getByText("Validate draft")).toBeInTheDocument();
    expect(screen.getByText("Review digest")).toBeInTheDocument();
    expect(screen.getByText("Queue build")).toBeInTheDocument();
    expect(screen.getByText("Built artifact")).toBeInTheDocument();

    expect(fetchSpy).toHaveBeenCalledWith("/api/control-plane/designs", expect.any(Object));
  });

  test("never shows password token or credential inputs", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ ok: true, items: [] }),
    );

    render(<StudioPageContent />);
    await screen.findByText(/no designs yet/i);

    expect(screen.queryByLabelText(/password|token|credential|organization/i)).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText(/password|token|credential|organization/i)).not.toBeInTheDocument();
  });
});
