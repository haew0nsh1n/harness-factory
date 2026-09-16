import { expect, test, type Page } from "@playwright/test";

const design = {
  id: "design-1",
  organization_id: "org-acme",
  customer_id: "customer-seoul",
  name: "리뷰 재작업 개선",
  profile: {
    facts: [
      {
        id: "fact-review",
        statement: "승인 기준의 차이로 리뷰 재작업이 발생합니다.",
      },
    ],
    assumptions: ["저장소에서 테스트 명령을 실행할 수 있다고 가정합니다."],
    unknowns: ["실제 저장소 접근 권한은 아직 확인되지 않았습니다."],
  },
  workflow: { name: "review-ready" },
  scenarios: { items: [] },
  catalog: { tools: [] },
  revision: 3,
  digest: "a".repeat(64),
  status: "draft",
  validation_findings: null,
  created_by: "author-1",
  created_at: "2026-09-15T00:00:00Z",
  updated_at: "2026-09-15T00:00:00Z",
};

async function mockStudioApi(page: Page): Promise<void> {
  await page.route("**/api/control-plane/designs", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true, items: [design] }),
    });
  });
  await page.route("**/api/control-plane/interviews", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true, items: [] }),
    });
  });
}

async function mockDesignApi(page: Page): Promise<void> {
  await page.route("**/api/control-plane/designs/design-1", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true, design }),
    });
  });
  await page.route("**/api/control-plane/interviews/catalog", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true, catalog: design.catalog }),
    });
  });
}

async function expectEvidenceNotClipped(page: Page): Promise<void> {
  const evidenceGroup = page.locator(".evidence-group:visible").first();
  const evidenceText = evidenceGroup.getByText(
    "승인 기준의 차이로 리뷰 재작업이 발생합니다.",
  );

  await expect(evidenceText).toBeVisible();
  const bounds = await evidenceGroup.evaluate((element) => {
    const group = element.getBoundingClientRect();
    const workspace = element
      .closest(".interview-workspace")
      ?.getBoundingClientRect();
    const text = element
      .querySelector("li p")
      ?.getBoundingClientRect();

    return {
      groupRight: group.right,
      textRight: text?.right ?? Number.POSITIVE_INFINITY,
      workspaceRight: workspace?.right ?? Number.NEGATIVE_INFINITY,
      viewportRight: window.innerWidth,
    };
  });

  expect(bounds.groupRight).toBeLessThanOrEqual(bounds.workspaceRight);
  expect(bounds.textRight).toBeLessThanOrEqual(bounds.workspaceRight);
  expect(bounds.groupRight).toBeLessThanOrEqual(bounds.viewportRight);
  expect(bounds.textRight).toBeLessThanOrEqual(bounds.viewportRight);
}

test.describe("mocked studio visual coverage", () => {
  for (const width of [320, 768, 1440]) {
    test(`studio fits ${width}px`, async ({ page }, testInfo) => {
      await mockStudioApi(page);
      await page.setViewportSize({ width, height: 1000 });
      await page.goto("/studio");

      await expect(page.getByRole("heading", { name: "스튜디오" })).toBeVisible();
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= window.innerWidth,
        ),
      ).toBe(true);
      await page.screenshot({
        path: testInfo.outputPath(`studio-${width}.png`),
        fullPage: true,
      });
    });

    test(`evidence workspace fits ${width}px`, async ({ page }, testInfo) => {
      await mockDesignApi(page);
      await page.setViewportSize({ width, height: 1100 });
      await page.goto("/studio/design-1");

      await expect(
        page.getByRole("heading", {
          name: "대화형 인터뷰는 아직 제공되지 않습니다.",
        }),
      ).toBeVisible();
      await expect(
        page
          .locator(".evidence-group:visible")
          .getByText("승인 기준의 차이로 리뷰 재작업이 발생합니다."),
      ).toBeVisible();
      await expect(page.getByText("답변 입력 미제공")).toBeVisible();
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= window.innerWidth,
        ),
      ).toBe(true);
      await page.screenshot({
        path: testInfo.outputPath(`workspace-${width}.png`),
        fullPage: true,
      });
    });
  }

  for (const width of [961, 1024, 1025]) {
    test(`evidence remains unclipped at ${width}px transition width`, async ({
      page,
    }, testInfo) => {
      await mockDesignApi(page);
      await page.setViewportSize({ width, height: 1100 });
      await page.goto("/studio/design-1");

      await expectEvidenceNotClipped(page);
      await page.screenshot({
        path: testInfo.outputPath(`workspace-transition-${width}.png`),
        fullPage: true,
      });
    });
  }

  test("keeps mobile navigation and a real design action keyboard reachable", async ({
    page,
  }) => {
    await mockStudioApi(page);
    await page.setViewportSize({ width: 320, height: 900 });
    await page.goto("/studio");

    for (const name of [
      "Harness Factory 홈",
      "대시보드",
      "스튜디오",
      "레지스트리",
      "새 AI 인터뷰",
      "리뷰 재작업 개선",
    ]) {
      await page.keyboard.press("Tab");
      const focused = page.getByRole("link", { name });
      await expect(focused).toBeFocused();
      await expect(focused).toBeVisible();
      const bounds = await focused.boundingBox();
      expect(bounds).not.toBeNull();
      expect(bounds?.x ?? -1).toBeGreaterThanOrEqual(0);
      expect((bounds?.x ?? 0) + (bounds?.width ?? 0)).toBeLessThanOrEqual(320);
    }
  });

  test("distinguishes an API failure from an empty studio", async ({ page }) => {
    await page.route("**/api/control-plane/designs", async (route) => {
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({
          ok: false,
          error: "설계 서비스에 연결할 수 없습니다.",
        }),
      });
    });
    await page.goto("/studio");

    await expect(
      page.getByRole("alert").filter({
        hasText: "설계 서비스에 연결할 수 없습니다.",
      }),
    ).toBeVisible();
    await expect(page.getByText("아직 저장된 설계가 없습니다.")).toHaveCount(0);
  });

  test("honors reduced motion preferences", async ({ page }) => {
    await mockDesignApi(page);
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/studio/design-1");

    expect(
      await page.evaluate(
        () => window.matchMedia("(prefers-reduced-motion: reduce)").matches,
      ),
    ).toBe(true);
    expect(
      await page.locator(".interview-workspace").evaluate((element) =>
        getComputedStyle(element)
          .transitionDuration.split(",")
          .every((duration) => Number.parseFloat(duration) <= 0.01),
      ),
    ).toBe(true);
  });

  test("gates the first model call behind explicit consent at 320px", async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width: 320, height: 1000 });
    await page.goto("/studio/interviews/new");

    const start = page.getByRole("button", { name: "인터뷰 시작" });
    await expect(start).toBeDisabled();
    await page.getByRole("checkbox", { name: /Azure OpenAI/ }).check();
    await expect(start).toBeEnabled();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: testInfo.outputPath("interview-consent-320.png"),
      fullPage: true,
    });
  });
});
