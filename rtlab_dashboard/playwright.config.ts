import { defineConfig } from "@playwright/test";

const port = Number(process.env.PLAYWRIGHT_PORT || 3100);
const externalBaseUrl = (process.env.PLAYWRIGHT_BASE_URL || "").trim();
const useLocalServer = !externalBaseUrl;
const baseURL = externalBaseUrl || `http://127.0.0.1:${port}`;
const npmRun = process.platform === "win32" ? "npm.cmd" : "npm";

export default defineConfig({
  testDir: "./tests/playwright",
  fullyParallel: false,
  workers: 1,
  timeout: 30_000,
  expect: {
    timeout: 10_000,
  },
  retries: process.env.CI ? 1 : 0,
  reporter: [["line"]],
  use: {
    baseURL,
    headless: true,
    trace: process.env.CI ? "on-first-retry" : "off",
    screenshot: "off",
    video: "off",
  },
  webServer: useLocalServer
    ? {
        command: `${npmRun} run dev -- --port ${port}`,
        cwd: __dirname,
        url: `${baseURL}/login`,
        reuseExistingServer: !process.env.CI,
        env: {
          ...process.env,
          NODE_ENV: "development",
          AUTH_SECRET: process.env.AUTH_SECRET || "playwright-local-auth-secret-1234567890",
          ADMIN_USERNAME: process.env.ADMIN_USERNAME || process.env.PLAYWRIGHT_USERNAME || "Wadmin",
          ADMIN_PASSWORD: process.env.ADMIN_PASSWORD || process.env.PLAYWRIGHT_PASSWORD || "moroco123",
          VIEWER_USERNAME: process.env.VIEWER_USERNAME || "viewer",
          VIEWER_PASSWORD: process.env.VIEWER_PASSWORD || "viewer123!",
          USE_MOCK_API: process.env.USE_MOCK_API || "true",
          ENABLE_MOCK_FALLBACK_ON_BACKEND_ERROR:
            process.env.ENABLE_MOCK_FALLBACK_ON_BACKEND_ERROR || "false",
          BACKEND_API_URL: process.env.PLAYWRIGHT_BACKEND_API_URL || process.env.BACKEND_API_URL || "",
          INTERNAL_PROXY_TOKEN:
            process.env.INTERNAL_PROXY_TOKEN || "playwright-local-internal-proxy-token-1234567890",
        },
      }
    : undefined,
});
