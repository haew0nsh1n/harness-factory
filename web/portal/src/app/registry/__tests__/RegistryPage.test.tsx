"use client";

import { render, screen } from "@testing-library/react";

import { RegistryPageContent } from "@/components/RegistryPageContent";

function jsonResponse(body: object): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

describe("RegistryPageContent", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  test("renders only published versions returned by the API", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        jsonResponse({
          ok: true,
          items: [
            {
              id: "asset-1",
              type: "workflow",
              slug: "issue-to-pr",
              name: "Issue to PR",
              description: "Automates issue to pull request flow.",
              versions: [
                { id: "v-1", version: "2.0.0", digest: "a".repeat(64), status: "published", channel: "stable", artifact_sha256: "1".repeat(64) },
                { id: "v-2", version: "2.1.0", digest: "b".repeat(64), status: "draft", channel: "unpublished", artifact_sha256: "2".repeat(64) }
              ]
            }
          ],
        }),
      );

    render(<RegistryPageContent />);

    expect(await screen.findByText("Issue to PR")).toBeInTheDocument();
    expect(screen.getByText("2.0.0")).toBeInTheDocument();
    expect(screen.queryByText("2.1.0")).not.toBeInTheDocument();
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/control-plane/registry/assets?type=workflow",
      expect.any(Object),
    );
  });

  test("never shows password token credential or organization selector inputs", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ ok: true, items: [] }),
    );

    render(<RegistryPageContent />);

    expect(await screen.findByText(/no published assets yet/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/password|token|credential|organization/i)).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText(/password|token|credential|organization/i)).not.toBeInTheDocument();
  });
});
