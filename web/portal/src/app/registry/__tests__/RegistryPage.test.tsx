"use client";

import { fireEvent, render, screen, waitFor } from "@testing-library/react";

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
    expect(screen.getByRole("searchbox", { name: "자산 검색" })).toBeInTheDocument();
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

    expect(await screen.findByText("게시된 워크플로가 없습니다.")).toBeInTheDocument();
    expect(screen.queryByLabelText(/password|token|credential|organization/i)).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText(/password|token|credential|organization/i)).not.toBeInTheDocument();
  });

  test("sends search and channel filters to the registry API", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(jsonResponse({ ok: true, items: [] }));

    render(<RegistryPageContent />);
    await screen.findByText("게시된 워크플로가 없습니다.");

    fireEvent.change(screen.getByRole("searchbox", { name: "자산 검색" }), {
      target: { value: "issue" },
    });
    fireEvent.change(screen.getByRole("combobox", { name: "배포 채널" }), {
      target: { value: "stable" },
    });

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledWith(
        "/api/control-plane/registry/assets?type=workflow&query=issue&channel=stable",
        expect.any(Object),
      );
    });
  });

  test("shows a failed initial request without claiming the registry is empty", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          ok: false,
          error: "레지스트리 서비스에 연결할 수 없습니다.",
        }),
        {
          status: 503,
          headers: { "content-type": "application/json" },
        },
      ),
    );

    render(<RegistryPageContent />);

    expect(
      await screen.findByRole("alert"),
    ).toHaveTextContent("레지스트리 서비스에 연결할 수 없습니다.");
    expect(
      screen.queryByText("게시된 워크플로가 없습니다."),
    ).not.toBeInTheDocument();
  });
});
