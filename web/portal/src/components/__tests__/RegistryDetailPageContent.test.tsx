import { fireEvent, render, screen } from "@testing-library/react";

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
    vi.unstubAllGlobals();
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
              {
                id: "version-2",
                version: "2.0.0",
                digest: "d".repeat(64),
                status: "published",
                channel: "stable",
                artifact_sha256: "e".repeat(64),
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
    expect(screen.getByRole("heading", { name: "로컬에 설치하기" })).toBeInTheDocument();
    const preview = "uv run --frozen --no-config --extra cli hf install issue-to-pr@1.0.0 --target ../your-repository";
    expect(screen.getByText(preview)).toBeInTheDocument();
    expect(screen.getByText(`${preview} --approve <preview-digest>`)).toBeInTheDocument();
    expect(screen.getByText("curl -LsSf https://astral.sh/uv/install.sh | sh")).toBeInTheDocument();
    expect(screen.getByText("uv run --frozen --no-config --extra cli hf login --registry <registry-url> --tenant <entra-tenant-id> --client-id <public-client-application-id> --scope api://<registry-api-app-id>/registry.access")).toBeInTheDocument();
    expect(screen.getByText("uv run --frozen --no-config --extra cli hf logout")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /명령 복사$/ })).toHaveLength(5);

    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    fireEvent.click(screen.getByRole("button", { name: "변경 미리보기 명령 복사" }));
    expect(writeText).toHaveBeenCalledWith(preview);
    expect(await screen.findByText("복사했습니다.")).toBeInTheDocument();

    writeText.mockRejectedValueOnce(new Error("Clipboard denied"));
    fireEvent.click(screen.getByRole("button", { name: "변경 미리보기 명령 복사" }));
    expect(await screen.findByText("복사하지 못했습니다. 명령을 직접 선택해 복사해 주세요.")).toBeInTheDocument();

    vi.stubGlobal("navigator", {});
    fireEvent.click(screen.getByRole("button", { name: "설치 적용 명령 복사" }));
    expect(await screen.findAllByText("복사하지 못했습니다. 명령을 직접 선택해 복사해 주세요.")).toHaveLength(2);

    fetchSpy.mockResolvedValueOnce(jsonResponse({
      schema_version: 1,
      asset: { type: "workflow", slug: "issue-to-pr" },
      version: "2.0.0",
      runtime: "copilot-cli",
      design_digest: "d".repeat(64),
      artifact: { sha256: "e".repeat(64), key: sentinelKey },
      dependencies: [],
    }));
    fireEvent.click(screen.getByRole("button", { name: /2\.0\.0/ }));
    expect(await screen.findByText("uv run --frozen --no-config --extra cli hf install issue-to-pr@2.0.0 --target ../your-repository")).toBeInTheDocument();
    expect(screen.getByText("uv run --frozen --no-config --extra cli hf install issue-to-pr@2.0.0 --target ../your-repository --approve <preview-digest>")).toBeInTheDocument();
    expect(screen.queryByText(preview)).not.toBeInTheDocument();
  });

  test("shows install guidance placeholder when there is no published version", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse({
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
        versions: [],
      },
    }));

    render(<RegistryDetailPageContent slug="issue-to-pr" />);

    expect(await screen.findByRole("heading", { name: "로컬에 설치하기" })).toBeInTheDocument();
    expect(screen.getByText("게시된 버전을 선택하면 설치 명령을 표시합니다.")).toBeInTheDocument();
    expect(screen.queryByText(/uv run/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /명령 복사$/ })).not.toBeInTheDocument();
  });
});
