import { defineConfig, devices } from "@playwright/test";

const port = Number(process.env.PLAYWRIGHT_PORT || 3100);

export default defineConfig({
  testDir: "./tests/playwright",
  timeout: 45_000,
  expect: {
    timeout: 10_000,
  },
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    command: `node ./node_modules/next/dist/bin/next dev --webpack --hostname 127.0.0.1 --port ${port}`,
    url: `http://127.0.0.1:${port}/login`,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    env: {
      APP_ENV: "local",
      USE_MOCK_API: "false",
      ENABLE_MOCK_FALLBACK_ON_BACKEND_ERROR: "false",
      AUTH_SECRET: "playwright-local-secret-for-read-only-smoke-1234567890",
      ADMIN_USERNAME: "admin",
      ADMIN_PASSWORD: "admin123!",
      VIEWER_USERNAME: "viewer",
      VIEWER_PASSWORD: "viewer123!",
    },
  },
});
