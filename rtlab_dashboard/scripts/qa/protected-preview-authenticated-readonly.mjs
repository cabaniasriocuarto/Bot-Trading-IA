import fs from "node:fs";
import path from "node:path";
import { chromium } from "@playwright/test";

const baseUrl = process.env.PREVIEW_URL;
const bypassSecret = process.env.BYPASS_SECRET;
const username = process.env.TEST_USERNAME;
const password = process.env.TEST_PASSWORD;
const reportDir = path.join("diagnostics", "rtlops109a-protected-preview-qa");

if (!baseUrl || !bypassSecret || !username || !password) {
  console.error(
    "Missing protected preview URL, bypass secret, or viewer QA credentials.",
  );
  process.exit(1);
}

const headers = {
  "x-vercel-protection-bypass": bypassSecret,
  "x-vercel-set-bypass-cookie": "true",
};

const routes = [
  "/",
  "/strategies",
  "/portfolio",
  "/backtests",
  "/execution",
  "/alerts",
  "/settings",
  "/risk",
  "/trades",
  "/reporting",
];

const apiPaths = [
  "/api/auth/me",
  "/api/v1/health",
  "/api/v1/portfolio",
  "/api/v1/positions",
  "/api/v1/bot/status",
  "/api/v1/strategies",
  "/api/v1/backtests/runs",
  "/api/v1/settings",
  "/api/v1/risk",
  "/api/v1/trades?limit=5000",
  "/api/v1/execution/metrics",
  "/api/v1/gates",
  "/api/v1/alerts",
  "/api/v1/logs",
  "/api/v1/reporting/performance/summary",
  "/api/v1/reporting/performance/daily",
  "/api/v1/reporting/performance/monthly",
  "/api/v1/reporting/costs/breakdown",
  "/api/v1/reporting/trades?limit=50",
  "/api/v1/reporting/exports?limit=20",
];

function bodySample(text) {
  return String(text || "")
    .replace(/\s+/g, " ")
    .slice(0, 260);
}

function isVercelSso(text) {
  const lower = String(text || "").toLowerCase();
  return (
    lower.includes("log in to vercel") ||
    lower.includes("vercel.com/sso-api") ||
    lower.includes("continue with github")
  );
}

async function safeInnerText(locator, timeout = 1_500) {
  return locator.innerText({ timeout }).catch(() => "");
}

async function collectButtons(page, terms) {
  const buttons = await page.locator("button").evaluateAll((nodes) =>
    nodes.map((node) => ({
      text: (node.textContent || "").replace(/\s+/g, " ").trim(),
      disabled: Boolean(node.disabled),
      ariaDisabled: node.getAttribute("aria-disabled") || "",
      type: node.getAttribute("type") || "",
    })),
  );
  return buttons.filter((button) =>
    terms.some((term) => button.text.toLowerCase().includes(term)),
  );
}

async function fetchStatus(page, apiPath) {
  return page.evaluate(async (targetPath) => {
    try {
      const response = await fetch(targetPath, {
        credentials: "include",
        cache: "no-store",
      });
      return {
        path: targetPath,
        status: response.status,
        contentType: response.headers.get("content-type") || "",
      };
    } catch (error) {
      return {
        path: targetPath,
        status: "FETCH_ERROR",
        error: String(error && error.message ? error.message : error),
      };
    }
  }, apiPath);
}

fs.mkdirSync(reportDir, { recursive: true });

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({
  viewport: { width: 1440, height: 1000 },
  extraHTTPHeaders: headers,
});

const consoleMessages = [];
const failedRequests = [];
const networkApiResponses = [];

page.on("console", (message) => {
  if (["error", "warning"].includes(message.type())) {
    consoleMessages.push({
      type: message.type(),
      text: message.text().slice(0, 240),
    });
  }
});

page.on("requestfailed", (request) => {
  failedRequests.push({
    url: request.url(),
    failure: request.failure()?.errorText || "",
  });
});

page.on("response", (response) => {
  const url = response.url();
  if (url.includes("/api/") || response.status() >= 400) {
    networkApiResponses.push({
      url,
      status: response.status(),
      contentType: response.headers()["content-type"] || "",
    });
  }
});

let loginStatus = "NOT_RUN";
let sessionUser = null;

try {
  await page.goto(new URL("/login", baseUrl).toString(), {
    waitUntil: "domcontentloaded",
    timeout: 45_000,
  });
  await page.locator("input").nth(0).fill(username);
  await page.locator("input").nth(1).fill(password);
  const [loginResponse] = await Promise.all([
    page.waitForResponse(
      (response) => response.url().includes("/api/auth/login"),
      { timeout: 20_000 },
    ),
    page.getByRole("button", { name: /ingresar/i }).click(),
  ]);
  loginStatus = loginResponse.status();
  await page.waitForTimeout(1_000);
  sessionUser = await page.evaluate(async () => {
    const response = await fetch("/api/auth/me", {
      credentials: "include",
      cache: "no-store",
    });
    const payload = await response.json().catch(() => ({}));
    return {
      status: response.status,
      usernamePresent: Boolean(payload && payload.username),
      role: payload && typeof payload.role === "string" ? payload.role : "",
    };
  });
} catch (error) {
  loginStatus = "ERROR";
  sessionUser = {
    status: "ERROR",
    error: String(error && error.message ? error.message : error).slice(0, 240),
  };
}

const routeResults = [];
const guardrails = {
  portfolio: {},
  execution: {},
  reporting: {},
};

if (sessionUser?.status === 200 && sessionUser?.role === "viewer") {
  for (const targetPath of routes) {
    const response = await page.goto(new URL(targetPath, baseUrl).toString(), {
      waitUntil: "domcontentloaded",
      timeout: 45_000,
    });
    await page.waitForTimeout(750);
    const body = await safeInnerText(page.locator("body"), 3_000);
    const h1 = await page
      .locator("h1")
      .first()
      .textContent({ timeout: 1_000 })
      .catch(() => "");
    routeResults.push({
      path: targetPath,
      status: response ? response.status() : "NO_RESPONSE",
      title: await page.title().catch(() => ""),
      h1: h1 || "",
      vercelSso: isVercelSso(body),
      bodySample: bodySample(body),
    });

    if (targetPath === "/portfolio") {
      guardrails.portfolio = {
        closeAllButtons: await collectButtons(page, [
          "cerrar todas",
          "close all",
        ]),
        visibleText: bodySample(body),
      };
    }

    if (targetPath === "/execution") {
      guardrails.execution = {
        dangerousButtons: await collectButtons(page, [
          "live",
          "kill",
          "start",
          "stop",
          "pausar",
          "reanudar",
          "cerrar",
          "orden",
          "comprar",
          "vender",
        ]),
        visibleText: bodySample(body),
      };
    }

    if (targetPath === "/reporting") {
      const hasCostos = /Costos/i.test(body);
      const hasReporting = /Reporting/i.test(body);
      guardrails.reporting = {
        hasCostosNav: hasCostos,
        hasReporting,
        hasReportingSemantics: hasCostos && hasReporting,
        hasTaxCommission: body.includes("taxCommission"),
        hasSpecialCommission: body.includes("specialCommission"),
        hasPendingCopy: body.toLowerCase().includes("pendiente"),
        hasUnsupportedCopy: body.toLowerCase().includes("no soportado"),
        visibleText: bodySample(body),
      };
    }
  }
}

const apiResults = [];
if (sessionUser?.status === 200 && sessionUser?.role === "viewer") {
  await page.goto(new URL("/", baseUrl).toString(), {
    waitUntil: "domcontentloaded",
    timeout: 45_000,
  });
  for (const apiPath of apiPaths) {
    apiResults.push(await fetchStatus(page, apiPath));
  }
}

await browser.close();

const report = {
  login: {
    status: loginStatus,
    sessionStatus: sessionUser?.status || "NO_SESSION",
    role: sessionUser?.role || "",
    usernamePresent: Boolean(sessionUser?.usernamePresent),
  },
  routes: routeResults,
  apiResults,
  guardrails,
  consoleMessages,
  failedRequests,
  networkApiResponses,
};

fs.writeFileSync(
  path.join(reportDir, "playwright-authenticated-readonly.json"),
  JSON.stringify(report, null, 2),
);

console.log("RTLOPS-112 viewer-authenticated read-only QA summary");
console.log(`login_status=${loginStatus}`);
console.log(`session_status=${sessionUser?.status || "NO_SESSION"}`);
console.log(`session_role=${sessionUser?.role || ""}`);
for (const item of routeResults) {
  console.log(
    `${item.path}\tstatus=${item.status}\tvercel_sso=${item.vercelSso}`,
  );
}
for (const item of apiResults) {
  console.log(`${item.path}\tstatus=${item.status}`);
}
if (guardrails.reporting && Object.keys(guardrails.reporting).length > 0) {
  for (const [name, passed] of Object.entries(guardrails.reporting)) {
    if (name === "visibleText") continue;
    console.log(`/reporting\t${name}=${passed}`);
  }
}

if (sessionUser?.status !== 200) {
  console.error("Viewer login did not produce an authenticated app session.");
  process.exit(1);
}

if (sessionUser.role !== "viewer") {
  console.error(
    "Expected viewer role for RTLOPS-112 authenticated read-only QA.",
  );
  process.exit(1);
}

const reportingRoute = routeResults.find((item) => item.path === "/reporting");
if (
  !reportingRoute ||
  reportingRoute.status !== 200 ||
  reportingRoute.vercelSso
) {
  console.error("Expected /reporting to load for viewer without Vercel SSO.");
  process.exit(1);
}

const requiredReportingChecks = [
  "hasCostosNav",
  "hasReporting",
  "hasReportingSemantics",
  "hasTaxCommission",
  "hasSpecialCommission",
  "hasPendingCopy",
  "hasUnsupportedCopy",
];
for (const checkName of requiredReportingChecks) {
  if (!guardrails.reporting?.[checkName]) {
    console.error(
      `/reporting missing expected read-only reporting marker: ${checkName}`,
    );
    process.exit(1);
  }
}
