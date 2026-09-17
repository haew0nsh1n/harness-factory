import { api, apiRaw, ApiError } from "@/lib/api";

describe("api", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  test("sends browser requests through the same-origin control-plane proxy", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        new Response(JSON.stringify({ ok: true, items: [] }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      );

    await api<{ items: unknown[] }>("/registry/assets?type=workflow");

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [url, init] = fetchSpy.mock.calls[0] ?? [];
    expect(url).toBe("/api/control-plane/registry/assets?type=workflow");
    expect(init?.credentials).toBe("same-origin");

    const headers = new Headers(init?.headers);
    expect(headers.get("authorization")).toBeNull();
    expect(headers.get("x-hf-organization")).toBeNull();
    expect(headers.get("x-hf-subject")).toBeNull();
    expect(headers.get("x-hf-roles")).toBeNull();
  });

  test("maps API error envelopes without exposing headers", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          ok: false,
          code: "invalid_lifecycle",
          error: "design lifecycle does not allow review",
        }),
        {
          status: 422,
          headers: {
            "content-type": "application/json",
            "x-secret-header": "hidden",
          },
        },
      ),
    );

    await expect(api("/designs/design-1/reviews", { method: "POST" })).rejects.toEqual(
      new ApiError(
        "invalid_lifecycle",
        "design lifecycle does not allow review",
        422,
        {
          ok: false,
          code: "invalid_lifecycle",
          error: "design lifecycle does not allow review",
        },
      ),
    );
  });

  test("preserves failed-validation finding payloads on the error", async () => {
    const finding = {
      field: "contract",
      code: "invalid-design",
      message: "validation: workflow: unknown step",
    };
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          ok: false,
          code: "invalid_design",
          error: "design validation failed",
          finding,
          design: { id: "design-1", validation_findings: [finding] },
        }),
        { status: 422, headers: { "content-type": "application/json" } },
      ),
    );

    const error = await api("/designs/design-1/validate", { method: "POST" }).catch(
      (cause: unknown) => cause,
    );

    expect(error).toBeInstanceOf(ApiError);
    const apiError = error as ApiError;
    expect(apiError.code).toBe("invalid_design");
    expect(apiError.payload?.finding).toEqual(finding);
    expect(apiError.payload?.design).toMatchObject({ id: "design-1" });
  });

  test("supports raw json responses for manifest requests only when explicitly used", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        new Response(
          JSON.stringify({
            schema_version: 1,
            asset: { type: "workflow", slug: "issue-to-pr" },
            version: "1.0.0",
            runtime: "copilot-cli",
            design_digest: "a".repeat(64),
            artifact: { sha256: "b".repeat(64), key: "opaque/key.tar" },
            dependencies: [],
          }),
          {
            status: 200,
            headers: { "content-type": "application/json" },
          },
        ),
      );

    const manifest = await apiRaw<{ version: string; artifact: { sha256: string } }>(
      "/registry/versions/version-1/manifest",
    );

    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/control-plane/registry/versions/version-1/manifest",
      expect.any(Object),
    );
    expect(manifest.version).toBe("1.0.0");
    expect(manifest.artifact.sha256).toBe("b".repeat(64));
  });

  test("keeps envelope validation for non-raw api requests", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          schema_version: 1,
          asset: { type: "workflow", slug: "issue-to-pr" },
        }),
        {
          status: 200,
          headers: { "content-type": "application/json" },
        },
      ),
    );

    await expect(api("/registry/versions/version-1/manifest")).rejects.toMatchObject({
      name: "ApiError",
      code: "request_failed",
      message: "Request failed",
      status: 500,
    });
  });

  test("supports DELETE through the same-origin proxy", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ ok: true, deleted: true }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );

    await api("/interviews/interview-1", { method: "DELETE" });

    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/control-plane/interviews/interview-1",
      expect.objectContaining({ method: "DELETE" }),
    );
  });
});
