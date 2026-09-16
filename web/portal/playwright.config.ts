import path from "node:path";

import { defineConfig, devices } from "@playwright/test";

const port = 4317;

export default defineConfig({
  testDir: ".",
  testMatch: ["tests/browser/**/*.spec.ts", "e2e/**/*.spec.ts"],
  testIgnore: ["e2e/**/*.integration.spec.ts"],
  outputDir: path.resolve(
    __dirname,
    "../../.superpowers/sdd/2026-09-15-ai-interview-forms/playwright-artifacts",
  ),
  fullyParallel: false,
  reporter: "line",
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    command: `NEXT_PUBLIC_HF_AUTH_MODE=development npm run dev -- --hostname 127.0.0.1 --port ${port}`,
    url: `http://127.0.0.1:${port}`,
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
