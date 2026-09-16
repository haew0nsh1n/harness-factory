import { render, screen } from "@testing-library/react";

import { RegistryDetailPageContent } from "@/components/RegistryDetailPageContent";

function jsonResponse(body: object): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

describe("RegistryDetailPageContent", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  test("loads asset detail and renders only approved manifest fields without artifact key", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const sentinelKey = "SENTINEL-DO-NOT-RENDER-ARTIFACT-KEY";
    fetchSpy
      .mockResolvedValueOnce(
        jsonResponse({
          ok: true,
          asset: {
            id: "asset-1",
            organization_id: "org-acme",
            type: "workflow",
            slug: "issue-to-pr",
            name: "Issue to PR",
            description: "Asset detail",
            owner_subject_id: "owner-1",
            visibility: "internal",
            lifecycle: "active",
            versions: [
              {
                id: "version-1",
                version: "1.0.0",
                digest: "a".repeat(64),
                status: "published",
                channel: "stable",
                artifact_sha256: "b".repeat(64),
              },
            ],
          },
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          schema_version: 1,
          asset: { type: "workflow", slug: "issue-to-pr" },
          version: "1.0.0",
          runtime: "copilot-cli",
          design_digest: "c".repeat(64),
          artifact: {
            sha256: "b".repeat(64),
            key: sentinelKey,
          },
          dependencies: [],
        }),
      );

    render(<RegistryDetailPageContent slug="issue-to-pr" />);

    expect(await screen.findByRole("heading", { name: "Issue to PR" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "게시 버전" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "변경 불가 매니페스트" })).toBeInTheDocument();
    expect(screen.getByText("검증: 검증됨")).toBeInTheDocument();
    expect(screen.getByText("승인: 승인됨")).toBeInTheDocument();
    expect(await screen.findByText("b".repeat(64))).toBeInTheDocument();
    const manifestBlock = await screen.findByText((_, element) =>
      element?.tagName === "PRE" &&
      (element.textContent ?? "").includes('"schema_version": 1') &&
      (element.textContent ?? "").includes('"slug": "issue-to-pr"') &&
      (element.textContent ?? "").includes('"version": "1.0.0"') &&
      (element.textContent ?? "").includes(`"artifact_sha256": "${"b".repeat(64)}"`),
    );
    expect(manifestBlock).toBeInTheDocument();
    expect(screen.queryByText(sentinelKey)).not.toBeInTheDocument();
    expect(manifestBlock.textContent).not.toContain('"key"');
    expect(fetchSpy).toHaveBeenNthCalledWith(
      2,
      "/api/control-plane/registry/versions/version-1/manifest",
      expect.any(Object),
    );
  });
});
