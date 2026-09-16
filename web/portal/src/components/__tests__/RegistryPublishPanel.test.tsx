import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { RegistryPublishPanel } from "@/components/RegistryPublishPanel";
import type { HarnessDesign, RegistryAssetSummary } from "@/lib/types";

const DESIGN_DIGEST = "a".repeat(64);
const VERSION_DIGEST = "b".repeat(64);
const ARTIFACT_DIGEST = "c".repeat(64);

function jsonResponse(body: object, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function designFixture(status: HarnessDesign["status"] = "built"): HarnessDesign {
  return {
    id: "design-1",
    organization_id: "org-acme",
    customer_id: "cust-1",
    name: "Issue delivery",
    language: "ko",
    profile: {},
    workflow: {
      id: "issue-to-reviewed-pr",
      goal: "Reduce acceptance rework without automating publication authority.",
    },
    scenarios: {},
    catalog: {},
    revision: 3,
    digest: DESIGN_DIGEST,
    status,
    validation_findings: null,
    created_by: "author-1",
    created_at: "2026-09-14T00:00:00Z",
    updated_at: "2026-09-14T00:00:00Z",
  };
}

function version(status = "draft", channel = "unpublished") {
  return {
    id: "version-1",
    organization_id: "org-acme",
    asset_id: "asset-1",
    version: "1.0.0",
    digest: VERSION_DIGEST,
    status,
    channel,
    artifact_sha256: ARTIFACT_DIGEST,
    manifest: {
      design_digest: DESIGN_DIGEST,
      artifact: { sha256: ARTIFACT_DIGEST },
    },
  };
}

function existingAsset(
  versions: RegistryAssetSummary["versions"] = [],
): RegistryAssetSummary {
  return {
    id: "asset-1",
    type: "workflow",
    slug: "issue-to-reviewed-pr",
    name: "Issue delivery",
    language: "ko",
    description:
      "Reduce acceptance rework without automating publication authority.",
    versions,
  };
}

describe("RegistryPublishPanel", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  test("is hidden before the design is built", () => {
    render(<RegistryPublishPanel design={designFixture("approved")} />);
    expect(
      screen.queryByRole("heading", { name: "레지스트리 등록" }),
    ).not.toBeInTheDocument();
  });

  test("loads built defaults and creates the asset with the current actor", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    fetchSpy
      .mockResolvedValueOnce(
        jsonResponse({
          ok: true,
          actor: {
            organization_id: "org-acme",
            subject_id: "consultant-42",
            roles: ["author", "reviewer", "registry-admin"],
          },
        }),
      )
      .mockResolvedValueOnce(jsonResponse({ ok: true, items: [] }))
      .mockResolvedValueOnce(
        jsonResponse({ ok: true, asset: { ...existingAsset(), versions: undefined } }, 201),
      );

    render(<RegistryPublishPanel design={designFixture()} />);

    expect(
      await screen.findByRole("heading", { name: "레지스트리 등록" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("레지스트리 슬러그")).toHaveValue(
      "issue-to-reviewed-pr",
    );
    expect(screen.getByLabelText("버전")).toHaveValue("1.0.0");
    expect(screen.getByLabelText("배포 채널")).toHaveValue("pilot");

    fireEvent.click(screen.getByRole("button", { name: "자산 준비" }));
    await screen.findByText("자산 준비 완료");

    expect(fetchSpy).toHaveBeenNthCalledWith(
      3,
      "/api/control-plane/registry/assets",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          type: "workflow",
          slug: "issue-to-reviewed-pr",
          name: "Issue delivery",
          language: "ko",
          description:
            "Reduce acceptance rework without automating publication authority.",
          owner_subject_id: "consultant-42",
        }),
      }),
    );
    expect(screen.getByLabelText("레지스트리 슬러그")).toBeDisabled();
    expect(screen.getByRole("button", { name: "등록 흐름 초기화" })).toBeEnabled();
  });

  test("reuses only the exact existing slug and creates the exact design version", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    fetchSpy
      .mockResolvedValueOnce(
        jsonResponse({
          ok: true,
          actor: {
            organization_id: "org-acme",
            subject_id: "consultant-42",
            roles: ["author", "reviewer", "registry-admin"],
          },
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          ok: true,
          items: [
            { ...existingAsset(), slug: "issue-to-reviewed-pr-extra" },
            existingAsset(),
          ],
        }),
      )
      .mockResolvedValueOnce(jsonResponse({ ok: true, version: version() }, 201));

    render(<RegistryPublishPanel design={designFixture()} />);
    await screen.findByRole("button", { name: "자산 준비" });
    fireEvent.click(screen.getByRole("button", { name: "자산 준비" }));
    expect(await screen.findByText("기존 자산을 사용합니다.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "버전 생성" }));
    await screen.findByText("버전 생성 완료");

    expect(fetchSpy).toHaveBeenNthCalledWith(
      3,
      "/api/control-plane/registry/assets/asset-1/versions",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          design_id: "design-1",
          design_digest: DESIGN_DIGEST,
          version: "1.0.0",
        }),
      }),
    );
    expect(screen.getByText(VERSION_DIGEST)).toBeInTheDocument();
    expect(screen.getByText(ARTIFACT_DIGEST)).toBeInTheDocument();
  });

  test("keeps registry review and publication as separate explicit actions", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    fetchSpy
      .mockResolvedValueOnce(
        jsonResponse({
          ok: true,
          actor: {
            organization_id: "org-acme",
            subject_id: "consultant-42",
            roles: ["author", "reviewer", "registry-admin"],
          },
        }),
      )
      .mockResolvedValueOnce(jsonResponse({ ok: true, items: [existingAsset()] }))
      .mockResolvedValueOnce(jsonResponse({ ok: true, version: version() }, 201))
      .mockResolvedValueOnce(
        jsonResponse({ ok: true, version: version("approved") }),
      )
      .mockResolvedValueOnce(
        jsonResponse({ ok: true, version: version("published", "stable") }),
      );

    render(<RegistryPublishPanel design={designFixture()} />);
    await screen.findByRole("button", { name: "자산 준비" });
    fireEvent.click(screen.getByRole("button", { name: "자산 준비" }));
    await screen.findByText("기존 자산을 사용합니다.");
    fireEvent.click(screen.getByRole("button", { name: "버전 생성" }));
    await screen.findByText("버전 생성 완료");

    expect(screen.getByRole("button", { name: "레지스트리 버전 승인" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "게시" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "레지스트리 버전 승인" }));
    await screen.findByText("레지스트리 버전 승인 완료");

    fireEvent.change(screen.getByLabelText("배포 채널"), {
      target: { value: "stable" },
    });
    fireEvent.click(screen.getByRole("button", { name: "게시" }));

    expect(await screen.findByRole("link", { name: "레지스트리에서 보기" }))
      .toHaveAttribute("href", "/registry/issue-to-reviewed-pr");
    expect(fetchSpy).toHaveBeenNthCalledWith(
      4,
      "/api/control-plane/registry/versions/version-1/reviews",
      expect.objectContaining({
        body: JSON.stringify({
          expected_digest: VERSION_DIGEST,
          decision: "approved",
        }),
      }),
    );
    expect(fetchSpy).toHaveBeenNthCalledWith(
      5,
      "/api/control-plane/registry/versions/version-1/publish",
      expect.objectContaining({
        body: JSON.stringify({
          expected_digest: VERSION_DIGEST,
          channel: "stable",
        }),
      }),
    );
  });

  test("does not silently reuse a conflicting version with a different digest", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        jsonResponse({
          ok: true,
          actor: {
            organization_id: "org-acme",
            subject_id: "consultant-42",
            roles: ["author", "reviewer", "registry-admin"],
          },
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          ok: true,
          items: [
            existingAsset([
              {
                id: "version-other",
                version: "1.0.0",
                digest: "d".repeat(64),
                status: "draft",
                channel: "unpublished",
                artifact_sha256: "e".repeat(64),
              },
            ]),
          ],
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({ ok: false, code: "conflict", error: "duplicate" }, 409),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          ok: true,
          items: [
            existingAsset([
              {
                id: "version-other",
                version: "1.0.0",
                digest: "d".repeat(64),
                status: "draft",
                channel: "unpublished",
                artifact_sha256: "e".repeat(64),
              },
            ]),
          ],
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          design_digest: "f".repeat(64),
          artifact: { sha256: "e".repeat(64) },
        }),
      );

    render(<RegistryPublishPanel design={designFixture()} />);
    await screen.findByRole("button", { name: "자산 준비" });
    fireEvent.click(screen.getByRole("button", { name: "자산 준비" }));
    await screen.findByText("기존 자산을 사용합니다.");
    fireEvent.click(screen.getByRole("button", { name: "버전 생성" }));

    expect(
      await screen.findByText(/같은 1.0.0 버전이 있지만 현재 설계와 일치하지 않습니다/),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "레지스트리 버전 승인" }),
    ).not.toBeEnabled();
  });

  test("recovers a duplicate only after verifying its manifest matches", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        jsonResponse({
          ok: true,
          actor: {
            organization_id: "org-acme",
            subject_id: "consultant-42",
            roles: ["author", "reviewer", "registry-admin"],
          },
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          ok: true,
          items: [existingAsset([version()])],
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({ ok: false, code: "conflict", error: "duplicate" }, 409),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          ok: true,
          items: [existingAsset([version()])],
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          design_digest: DESIGN_DIGEST,
          artifact: { sha256: ARTIFACT_DIGEST },
        }),
      );

    render(<RegistryPublishPanel design={designFixture()} />);
    await screen.findByRole("button", { name: "자산 준비" });
    fireEvent.click(screen.getByRole("button", { name: "자산 준비" }));
    await screen.findByText("기존 자산을 사용합니다.");
    fireEvent.click(screen.getByRole("button", { name: "버전 생성" }));

    expect(
      await screen.findByText("기존 1.0.0 버전이 현재 설계와 일치해 다시 불러왔습니다."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "레지스트리 버전 승인" })).toBeEnabled();
  });

  test("refreshes registry assets before recovering a version created after initial load", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    fetchSpy
      .mockResolvedValueOnce(
        jsonResponse({
          ok: true,
          actor: {
            organization_id: "org-acme",
            subject_id: "consultant-42",
            roles: ["author", "reviewer", "registry-admin"],
          },
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          ok: true,
          items: [existingAsset()],
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({ ok: false, code: "conflict", error: "duplicate" }, 409),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          ok: true,
          items: [existingAsset([version()])],
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          design_digest: DESIGN_DIGEST,
          artifact: { sha256: ARTIFACT_DIGEST },
        }),
      );

    render(<RegistryPublishPanel design={designFixture()} />);
    await screen.findByRole("button", { name: "자산 준비" });
    fireEvent.click(screen.getByRole("button", { name: "자산 준비" }));
    await screen.findByText("기존 자산을 사용합니다.");
    fireEvent.click(screen.getByRole("button", { name: "버전 생성" }));

    expect(
      await screen.findByText("기존 1.0.0 버전이 현재 설계와 일치해 다시 불러왔습니다."),
    ).toBeInTheDocument();
    expect(fetchSpy).toHaveBeenNthCalledWith(
      4,
      "/api/control-plane/registry/assets?type=workflow",
      expect.anything(),
    );
    expect(screen.getByRole("button", { name: "레지스트리 버전 승인" })).toBeEnabled();
  });

  test("disables duplicate actions while a request is busy", async () => {
    let resolveCreate: ((response: Response) => void) | undefined;
    const pendingCreate = new Promise<Response>((resolve) => {
      resolveCreate = resolve;
    });
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        jsonResponse({
          ok: true,
          actor: {
            organization_id: "org-acme",
            subject_id: "consultant-42",
            roles: ["author", "reviewer", "registry-admin"],
          },
        }),
      )
      .mockResolvedValueOnce(jsonResponse({ ok: true, items: [] }))
      .mockReturnValueOnce(pendingCreate);

    render(<RegistryPublishPanel design={designFixture()} />);
    const prepare = await screen.findByRole("button", { name: "자산 준비" });
    fireEvent.click(prepare);

    await waitFor(() => expect(prepare).toBeDisabled());
    expect(screen.getByRole("button", { name: "버전 생성" })).toBeDisabled();
    resolveCreate?.(
      jsonResponse({ ok: true, asset: { ...existingAsset(), versions: undefined } }, 201),
    );
    await screen.findByText("자산 준비 완료");
  });
});
