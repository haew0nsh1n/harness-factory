"use client";

import { render, screen, waitFor, within } from "@testing-library/react";

import { DashboardPageContent } from "@/components/DashboardPageContent";

function jsonResponse(body: object): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

describe("DashboardPageContent", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  test("shows separate validated approved built and published counts", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation((input) => {
        const url = String(input);
        if (url === "/api/control-plane/designs") {
          return Promise.resolve(
            jsonResponse({
              ok: true,
              items: [
                { id: "d-1", customer_id: "cust-1", name: "Draft", profile: {}, workflow: {}, scenarios: {}, catalog: {}, revision: 1, digest: "a".repeat(64), status: "draft", validation_findings: null, organization_id: "org-acme", created_by: "author-1", created_at: "2026-09-14T00:00:00Z", updated_at: "2026-09-14T00:00:00Z" },
                { id: "d-2", customer_id: "cust-1", name: "Validated", profile: {}, workflow: {}, scenarios: {}, catalog: {}, revision: 2, digest: "b".repeat(64), status: "validated", validation_findings: [], organization_id: "org-acme", created_by: "author-1", created_at: "2026-09-14T00:00:00Z", updated_at: "2026-09-14T00:00:00Z" },
                { id: "d-3", customer_id: "cust-1", name: "Approved", profile: {}, workflow: {}, scenarios: {}, catalog: {}, revision: 3, digest: "c".repeat(64), status: "approved", validation_findings: [], organization_id: "org-acme", created_by: "author-1", created_at: "2026-09-14T00:00:00Z", updated_at: "2026-09-14T00:00:00Z" },
                { id: "d-4", customer_id: "cust-1", name: "Built", profile: {}, workflow: {}, scenarios: {}, catalog: {}, revision: 4, digest: "d".repeat(64), status: "built", validation_findings: [], organization_id: "org-acme", created_by: "author-1", created_at: "2026-09-14T00:00:00Z", updated_at: "2026-09-14T00:00:00Z" }
              ],
            }),
          );
        }
        if (url === "/api/control-plane/registry/assets?type=workflow") {
          return Promise.resolve(
            jsonResponse({
              ok: true,
              items: [
                {
                  id: "asset-1",
                  type: "workflow",
                  slug: "alpha",
                  name: "Alpha",
                  description: "First",
                  versions: [
                    { id: "v-1", version: "1.0.0", digest: "e".repeat(64), status: "published", channel: "pilot", artifact_sha256: "1".repeat(64) },
                    { id: "v-2", version: "1.0.1", digest: "f".repeat(64), status: "approved", channel: "unpublished", artifact_sha256: "2".repeat(64) }
                  ]
                },
                {
                  id: "asset-2",
                  type: "workflow",
                  slug: "beta",
                  name: "Beta",
                  description: "Second",
                  versions: [
                    { id: "v-3", version: "2.0.0", digest: "0".repeat(64), status: "published", channel: "stable", artifact_sha256: "3".repeat(64) }
                  ]
                }
              ],
            }),
          );
        }
        return Promise.reject(new Error(`unexpected url: ${url}`));
      });

    render(<DashboardPageContent />);

    const validatedCard = await screen.findByRole("heading", { name: "검증됨" });
    expect(validatedCard).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText("검증됨")).toBeInTheDocument();
      expect(screen.getByText("승인됨")).toBeInTheDocument();
      expect(screen.getByText("빌드 완료")).toBeInTheDocument();
      expect(screen.getByText("게시됨")).toBeInTheDocument();
    });
    expect(within(validatedCard.closest("section") as HTMLElement).getByText("1")).toBeInTheDocument();
    expect(
      within(screen.getByRole("heading", { name: "승인됨" }).closest("section") as HTMLElement).getByText("1"),
    ).toBeInTheDocument();
    expect(
      within(screen.getByRole("heading", { name: "빌드 완료" }).closest("section") as HTMLElement).getByText("1"),
    ).toBeInTheDocument();
    expect(
      within(
        screen.getByRole("heading", { name: "빌드 완료" }).closest(
          "section",
        ) as HTMLElement,
      ).getByText("빌드 처리 완료"),
    ).toBeInTheDocument();
    expect(screen.queryByText("게시 준비 완료")).not.toBeInTheDocument();
    expect(
      within(screen.getByRole("heading", { name: "게시됨" }).closest("section") as HTMLElement).getByText("2"),
    ).toBeInTheDocument();

    expect(fetchSpy).toHaveBeenCalledWith("/api/control-plane/designs", expect.any(Object));
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/control-plane/registry/assets?type=workflow",
      expect.any(Object),
    );
  });
});
