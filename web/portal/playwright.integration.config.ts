import { defineConfig, devices } from "@playwright/test";

const apiPort = 4328;
const portalPort = 4329;

export default defineConfig({
  testDir: "e2e",
  testMatch: ["interview.integration.spec.ts"],
  fullyParallel: false,
  reporter: "line",
  use: {
    baseURL: `http://127.0.0.1:${portalPort}`,
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: [
    {
      command:
        "cd ../.. && rm -f .harness-factory/playwright-interview.db && " +
        "uv run --frozen --no-config uvicorn " +
        "web.acceptance.portal_interview_app:create_integration_app --factory " +
        `--host 127.0.0.1 --port ${apiPort}`,
      url: `http://127.0.0.1:${apiPort}/api/health`,
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command:
        "NEXT_PUBLIC_HF_AUTH_MODE=development " +
        `HF_API_BASE_URL=http://127.0.0.1:${apiPort} ` +
        "HF_DEV_ORGANIZATION=local-dev HF_DEV_SUBJECT=portal-dev " +
        "HF_DEV_ROLES=author,reviewer,registry-admin,developer,org-admin " +
        `npm run dev -- --hostname 127.0.0.1 --port ${portalPort}`,
      url: `http://127.0.0.1:${portalPort}`,
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});
