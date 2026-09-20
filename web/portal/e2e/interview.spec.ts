import { expect, test, type Page } from "@playwright/test";

import catalog from "../../../catalog/catalog.json";
import profile from "../../../examples/github-issue/profile.json";
import scenarios from "../../../examples/github-issue/scenarios.json";
import workflow from "../../../examples/github-issue/workflow.json";

const now = "2026-09-15T06:00:00Z";
const digest = "a".repeat(64);
const targetDigest = "b".repeat(64);

function session(overrides: Record<string, unknown> = {}) {
  return {
    id: "interview-e2e",
    organization_id: "local-dev",
    owner_subject_id: "portal-dev",
    name: "합성 리뷰 인터뷰",
    customer_id: "synthetic-team",
    revision: 1,
    status: "active",
    consent_version: "2026-09-15",
    consented_at: now,
    stage: "planning",
    selected_stages: ["planning", "implementation", "review"],
    scope: null,
    proposed_evidence: [],
    confirmed_evidence: [],
    turns: [
      {
        id: "turn-question",
        role: "assistant",
        text: "어느 합성 SDLC 인계에서 재작업이 가장 많이 발생하나요?",
        sequence: 1,
        created_at: now,
      },
    ],
    proposals: [],
    last_operation: null,
    last_error_code: null,
    created_at: now,
    updated_at: now,
    expires_at: "2026-10-15T06:00:00Z",
    ...overrides,
  };
}

const proposal = {
  id: "proposal-e2e",
  revision: 3,
  digest,
  status: "draft",
  findings: [],
  profile,
  workflow: Object.fromEntries(
    Object.entries(workflow).filter(([key]) => key !== "approved"),
  ),
  scenarios,
  catalog,
  created_at: now,
  updated_at: now,
};

const proposalSummary = {
  id: proposal.id,
  revision: proposal.revision,
  digest: proposal.digest,
  status: proposal.status,
  findings: proposal.findings,
  created_at: proposal.created_at,
  updated_at: proposal.updated_at,
};

const targetDesign = {
  id: "design-target",
  organization_id: "local-dev",
  customer_id: "synthetic-team",
  name: "기존 합성 설계",
  profile,
  workflow,
  scenarios,
  catalog,
  revision: 4,
  digest: targetDigest,
  status: "draft",
  validation_findings: [],
  created_by: "portal-dev",
  created_at: now,
  updated_at: now,
};

async function mockInterviewApi(page: Page): Promise<void> {
  let current: Record<string, any> = session();
  await page.route("**/api/control-plane/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace("/api/control-plane", "");
    const method = request.method();

    if (path === "/interviews" && method === "POST") {
      expect(request.postDataJSON()).toMatchObject({
        selected_stages: ["planning", "implementation", "review"],
      });
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({ ok: true, session: current }),
      });
      return;
    }
    if (path === "/interviews/interview-e2e" && method === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true, session: current }),
      });
      return;
    }
    if (path === "/designs" && method === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true, items: [targetDesign] }),
      });
      return;
    }
    if (path.endsWith("/turns") && method === "POST") {
      current = session({
        revision: 2,
        status: "awaiting-confirmation",
        stage: "summary",
        scope: "issue-to-reviewed-pr",
        proposed_evidence: [
          {
            id: "evidence-e2e",
            statement: "합성 팀은 구현 전에 리뷰 기준을 확인합니다.",
            kind: "fact",
            source_turn_ids: ["turn-answer"],
          },
        ],
        turns: [
          ...session().turns,
          {
            id: "turn-answer",
            role: "user",
            text: "합성 팀에서는 모호한 리뷰 기준 때문에 구현 재작업이 반복됩니다.",
            sequence: 2,
            created_at: now,
          },
          {
            id: "turn-review",
            role: "assistant",
            text: "이 합성 워크플로 범위를 검토할까요?",
            sequence: 3,
            created_at: now,
          },
        ],
      });
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true, session: current }),
      });
      return;
    }
    if (path.endsWith("/confirmations") && method === "POST") {
      current = {
        ...current,
        revision: 3,
        status: "active",
        proposed_evidence: [],
        confirmed_evidence: [
          {
            id: "evidence-e2e",
            statement: "합성 팀은 구현 전에 리뷰 기준을 확인합니다.",
            kind: "fact",
            source_turn_ids: ["turn-answer"],
          },
        ],
      };
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true, session: current }),
      });
      return;
    }
    if (path.endsWith("/proposals") && method === "POST") {
      current = {
        ...current,
        status: "completed",
        proposals: [proposalSummary],
      };
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({ ok: true, proposal }),
      });
      return;
    }
    if (path.endsWith("/proposals/proposal-e2e") && method === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true, proposal }),
      });
      return;
    }
    if (path.endsWith("/apply") && method === "POST") {
      expect(request.postDataJSON()).toEqual({
        expected_revision: proposal.revision,
        proposal_id: proposal.id,
        expected_proposal_digest: proposal.digest,
        confirm_scope: true,
        design_id: targetDesign.id,
        expected_design_digest: targetDesign.digest,
      });
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          design: { ...targetDesign, digest: "c".repeat(64) },
        }),
      });
      return;
    }
    if (path === "/designs/design-target" && method === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          design: { ...targetDesign, digest: "c".repeat(64) },
        }),
      });
      return;
    }
    if (path === "/interviews/catalog" && method === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true, catalog }),
      });
      return;
    }
    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ ok: false, error: `unhandled ${method} ${path}` }),
    });
  });
}

for (const width of [320, 768, 1440]) {
  test(`[mocked visual] interview proposal journey fits ${width}px`, async ({
    page,
  }, testInfo) => {
    await mockInterviewApi(page);
    await page.setViewportSize({ width, height: 1100 });
    await page.goto("/studio/interviews/new");

    await page.getByLabel("인터뷰 이름").fill("합성 리뷰 인터뷰");
    await page.getByLabel("고객 ID").fill("synthetic-team");
    await page.getByRole("checkbox", { name: /Azure OpenAI/ }).check();
    await page.getByRole("button", { name: "인터뷰 시작" }).click();
    await expect(page).toHaveURL(/\/studio\/interviews\/interview-e2e$/);

    await page.getByLabel("답변").fill(
      "합성 팀에서는 모호한 리뷰 기준 때문에 구현 재작업이 반복됩니다.",
    );
    await page.getByRole("button", { name: "답변 보내기" }).click();
    const evidenceReview = page
      .getByRole("heading", { name: "제안된 근거 결정" })
      .locator("..");
    await expect(
      evidenceReview.getByText("합성 팀은 구현 전에 리뷰 기준을 확인합니다."),
    ).toBeVisible();
    await evidenceReview.getByRole("button", { name: "사실 확인" }).click();
    await page.getByRole("button", { name: "설계 제안 생성" }).click();
    await expect(page.getByText(digest)).toBeVisible();
    await expect(page.getByLabel("프로필 전체 JSON 검토")).toHaveAttribute(
      "readonly",
    );

    await page.reload();
    await expect(page.getByText(digest)).toBeVisible();
    await page.getByLabel("적용 대상").selectOption("design-target");
    await expect(page.getByText(targetDigest)).toBeVisible();

    if (width <= 768) {
      await page.getByRole("tab", { name: "제안" }).click();
      await expect(
        page.getByRole("tabpanel", { name: "제안" }),
      ).toBeVisible();
    }
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: testInfo.outputPath(`interview-${width}.png`),
      fullPage: true,
    });

    await page.getByRole("checkbox", { name: /제안 aaaaaaaaaaaa/ }).check();
    await page.getByRole("button", { name: "디자인 등록" }).click();
    await expect(page).toHaveURL(/\/studio\/design-target$/);
  });
}
