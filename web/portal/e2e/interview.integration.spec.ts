import { expect, test, type APIResponse, type Page } from "@playwright/test";

type Design = {
  id: string;
  name: string;
  digest: string;
  revision: number;
  status: string;
  validation_findings: unknown[];
};

async function controlPlane<T>(
  page: Page,
  path: string,
  options: { method?: string; data?: unknown } = {},
): Promise<{ response: APIResponse; body: T }> {
  const response = await page.request.fetch(`/api/control-plane${path}`, options);
  return { response, body: (await response.json()) as T };
}

test("real portal proxy persists proposal into the selected SQLite target", async ({
  page,
}) => {
  const designsBefore = await controlPlane<{ ok: true; items: Design[] }>(
    page,
    "/designs",
  );
  expect(designsBefore.response.ok()).toBe(true);
  const target = designsBefore.body.items.find(
    (item) => item.name === "Existing synthetic design",
  );
  expect(target).toBeDefined();
  expect(target?.status).toBe("approved");
  const approvalsBefore = await controlPlane<{
    ok: true;
    design_id: string;
    approval_count: number;
    database: string;
  }>(page, `/acceptance/designs/${target!.id}/approval-count`);
  expect(approvalsBefore.body).toMatchObject({
    design_id: target!.id,
    approval_count: 1,
    database: "sqlite",
  });

  await page.goto("/studio/interviews/new");
  await page.getByLabel("인터뷰 이름").fill("Synthetic persisted interview");
  await page.getByLabel("고객 ID").fill("synthetic-team");
  await page.getByRole("checkbox", { name: /Azure OpenAI/ }).check();
  await page.getByRole("button", { name: "인터뷰 시작" }).click();
  await expect(page).toHaveURL(/\/studio\/interviews\/[0-9a-f-]+$/);

  await page
    .getByLabel("답변")
    .fill(
      "In this fictional team, unclear review criteria cause implementation rework.",
    );
  await page.getByRole("button", { name: "답변 보내기" }).click();
  const evidenceReview = page
    .getByRole("heading", { name: "제안된 근거 결정" })
    .locator("..");
  await expect(
    evidenceReview.getByText(
      "Fictional review criteria are clarified before implementation.",
    ),
  ).toBeVisible();
  await evidenceReview.getByRole("button", { name: "사실 확인" }).click();
  await page.getByRole("button", { name: "설계 제안 생성" }).click();

  const proposalDigest = page
    .locator("code")
    .filter({ hasText: /^[0-9a-f]{64}$/ })
    .first();
  await expect(proposalDigest).toBeVisible();
  const digest = (await proposalDigest.textContent())?.trim();
  expect(digest).toMatch(/^[0-9a-f]{64}$/);

  await page.reload();
  await expect(page.getByText(digest!)).toBeVisible();
  await page.getByLabel("적용 대상").selectOption(target!.id);
  await expect(page.getByText(target!.digest)).toBeVisible();
  await page
    .getByRole("checkbox", {
      name: new RegExp(`제안 ${digest!.slice(0, 12)}`),
    })
    .check();
  await page.getByRole("button", { name: "정확한 제안 적용" }).click();
  await expect(page).toHaveURL(new RegExp(`/studio/${target!.id}$`));

  const persisted = await controlPlane<{ ok: true; design: Design }>(
    page,
    `/designs/${target!.id}`,
  );
  expect(persisted.response.ok()).toBe(true);
  expect(persisted.body.design.id).toBe(target!.id);
  expect(persisted.body.design.revision).toBe(target!.revision + 1);
  expect(persisted.body.design.status).toBe("draft");
  expect(persisted.body.design.digest).not.toBe(target!.digest);
  const approvalsAfter = await controlPlane<{
    ok: true;
    design_id: string;
    approval_count: number;
    database: string;
  }>(page, `/acceptance/designs/${target!.id}/approval-count`);
  expect(approvalsAfter.body).toMatchObject({
    design_id: target!.id,
    approval_count: 0,
    database: "sqlite",
  });

  const validated = await controlPlane<{ ok: true; design: Design }>(
    page,
    `/designs/${target!.id}/validate`,
    { method: "POST" },
  );
  expect(validated.response.ok()).toBe(true);
  expect(validated.body.design.status).toBe("validated");
  expect(validated.body.design.validation_findings).toEqual([]);

  const buildWithoutFreshApproval = await controlPlane<{
    ok: false;
    code: string;
  }>(page, `/designs/${target!.id}/builds`, {
    method: "POST",
    data: { expected_digest: validated.body.design.digest },
  });
  expect(buildWithoutFreshApproval.response.status()).toBe(422);
  expect(buildWithoutFreshApproval.body.code).toBe("invalid_lifecycle");
  console.log(
    JSON.stringify({
      database: approvalsAfter.body.database,
      target_id_before: target!.id,
      target_id_after: persisted.body.design.id,
      revision_before: target!.revision,
      revision_after: persisted.body.design.revision,
      approval_count_before: approvalsBefore.body.approval_count,
      approval_count_after: approvalsAfter.body.approval_count,
      validated_status: validated.body.design.status,
      build_without_fresh_approval: buildWithoutFreshApproval.body.code,
    }),
  );
});
