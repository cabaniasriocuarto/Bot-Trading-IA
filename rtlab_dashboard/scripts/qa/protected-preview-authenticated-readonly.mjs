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

function hasAny(text, patterns) {
  return patterns.some((pattern) => pattern.test(text));
}

function textWindow(text, pattern, maxLength = 2_400) {
  const match = pattern.exec(text);
  return match ? text.slice(match.index, match.index + maxLength) : "";
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
  trades: {},
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
      const hasCostNetBlock = /Costos\s+y\s+PnL\s+neto/i.test(body);
      const hasGrossPnl = hasAny(body, [/Gross\s+PnL/i, /PnL\s+bruto/i]);
      const hasNetPnl = hasAny(body, [/Net\s+PnL/i, /PnL\s+neto/i]);
      const hasTotalCosts = /Costos\s+totales/i.test(body);
      const hasHonestCostStatusCopy = hasAny(body, [
        /pendiente/i,
        /no disponible/i,
        /no aplica/i,
        /no soportado/i,
        /unknown/i,
        /disponible/i,
        /parcial/i,
      ]);
      const hasReportingLink =
        (await page.locator('a[href="/reporting"]').count()) > 0;
      guardrails.portfolio = {
        closeAllButtons: await collectButtons(page, [
          "cerrar todas",
          "close all",
        ]),
        hasCostNetBlock,
        hasGrossPnl,
        hasNetPnl,
        hasTotalCosts,
        hasReportingLink,
        hasHonestCostStatusCopy,
        hasPortfolioCostSemantics:
          hasCostNetBlock &&
          hasGrossPnl &&
          hasNetPnl &&
          hasTotalCosts &&
          hasReportingLink &&
          hasHonestCostStatusCopy,
        visibleText: bodySample(body),
      };
    }

    if (targetPath === "/trades") {
      const hasCostStackCompact = hasAny(body, [
        /Cost\s+Stack\s+compacto/i,
        /Cost\s+Stack/i,
      ]);
      const hasCostos = /Costos/i.test(body);
      const hasGrossPnl = hasAny(body, [/PnL\s+bruto/i, /gross\s+pnl/i]);
      const hasNetPnl = hasAny(body, [/PnL\s+neto/i, /net\s+pnl/i]);
      const hasFees = /\bfees?\b/i.test(body);
      const hasSlippage = /slippage/i.test(body);
      const hasReportingLink =
        (await page.locator('a[href="/reporting"]').count()) > 0;
      guardrails.trades = {
        hasCostStackCompact,
        hasCostos,
        hasGrossPnl,
        hasNetPnl,
        hasFees,
        hasSlippage,
        hasReportingLink,
        hasTradesCostStackSemantics:
          hasCostStackCompact &&
          hasCostos &&
          hasGrossPnl &&
          hasNetPnl &&
          hasFees &&
          hasSlippage &&
          hasReportingLink,
        visibleText: bodySample(body),
      };
    }

    if (targetPath === "/execution") {
      const hasExecutionCostStack = hasAny(body, [
        /Costos\s+operativos/i,
        /Cost\s+Stack/i,
      ]);
      const hasExecutionReportingLink =
        (await page.locator('a[href="/reporting"]').count()) > 0;
      const hasExecutionReadOnlyCopy = /Read-only/i.test(body);
      const hasExecutionNoLiveGateCopy =
        /no habilita submit real/i.test(body) ||
        /no modifica gates/i.test(body) ||
        /No usar como senal de habilitacion LIVE/i.test(body);
      const executionCostStackText = textWindow(
        body,
        /Costos\s+operativos\s*\/\s*Cost\s+Stack/i,
      );
      const hasMissingEvidenceCopy = hasAny(executionCostStackText, [
        /pendiente/i,
        /no disponible/i,
        /no aplica/i,
        /sin dato/i,
      ]);
      const hasNoInventedZeroCostStack = !/(?:US\$|\$)\s*0(?:[,.]00)?/.test(
        executionCostStackText,
      );
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
        hasCostStackOperationalCard: hasExecutionCostStack,
        hasReportingLink: hasExecutionReportingLink,
        hasReadOnlyCopy: hasExecutionReadOnlyCopy,
        hasNoLiveGateCopy: hasExecutionNoLiveGateCopy,
        hasMissingEvidenceCopy,
        hasNoInventedZeroCostStack,
        hasExecutionCostStackSemantics:
          hasExecutionCostStack &&
          hasExecutionReportingLink &&
          hasExecutionReadOnlyCopy &&
          hasExecutionNoLiveGateCopy &&
          hasMissingEvidenceCopy &&
          hasNoInventedZeroCostStack,
        visibleText: bodySample(body),
      };
    }

    if (targetPath === "/reporting") {
      const hasCostos = /Costos/i.test(body);
      const hasReporting = /Reporting/i.test(body);
      const hasCommissionStatusCopy =
        /pendiente/i.test(body) ||
        /disponible/i.test(body) ||
        /parcial/i.test(body) ||
        /\bsoportado\b/i.test(body) ||
        /no soportado/i.test(body) ||
        /no aplica/i.test(body);
      guardrails.reporting = {
        hasCostosNav: hasCostos,
        hasReporting,
        hasReportingSemantics: hasCostos && hasReporting,
        hasTaxCommission: body.includes("taxCommission"),
        hasSpecialCommission: body.includes("specialCommission"),
        hasPendingCopy: body.toLowerCase().includes("pendiente"),
        hasUnsupportedCopy: body.toLowerCase().includes("no soportado"),
        hasCommissionStatusCopy,
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
if (guardrails.trades && Object.keys(guardrails.trades).length > 0) {
  for (const [name, passed] of Object.entries(guardrails.trades)) {
    if (name === "visibleText") continue;
    console.log(`/trades\t${name}=${passed}`);
  }
}
if (guardrails.portfolio && Object.keys(guardrails.portfolio).length > 0) {
  for (const [name, passed] of Object.entries(guardrails.portfolio)) {
    if (name === "visibleText" || name === "closeAllButtons") continue;
    console.log(`/portfolio\t${name}=${passed}`);
  }
}
if (guardrails.execution && Object.keys(guardrails.execution).length > 0) {
  for (const [name, passed] of Object.entries(guardrails.execution)) {
    if (name === "visibleText" || name === "dangerousButtons") continue;
    console.log(`/execution\t${name}=${passed}`);
  }
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

const tradesRoute = routeResults.find((item) => item.path === "/trades");
if (!tradesRoute || tradesRoute.status !== 200 || tradesRoute.vercelSso) {
  console.error("Expected /trades to load for viewer without Vercel SSO.");
  process.exit(1);
}

const portfolioRoute = routeResults.find((item) => item.path === "/portfolio");
if (
  !portfolioRoute ||
  portfolioRoute.status !== 200 ||
  portfolioRoute.vercelSso
) {
  console.error("Expected /portfolio to load for viewer without Vercel SSO.");
  process.exit(1);
}

const executionRoute = routeResults.find((item) => item.path === "/execution");
if (
  !executionRoute ||
  executionRoute.status !== 200 ||
  executionRoute.vercelSso
) {
  console.error("Expected /execution to load for viewer without Vercel SSO.");
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

const requiredTradesChecks = [
  "hasCostStackCompact",
  "hasCostos",
  "hasGrossPnl",
  "hasNetPnl",
  "hasFees",
  "hasSlippage",
  "hasReportingLink",
  "hasTradesCostStackSemantics",
];
for (const checkName of requiredTradesChecks) {
  if (!guardrails.trades?.[checkName]) {
    console.error(
      `/trades missing expected compact Cost Stack marker: ${checkName}`,
    );
    process.exit(1);
  }
}

const requiredPortfolioChecks = [
  "hasCostNetBlock",
  "hasGrossPnl",
  "hasNetPnl",
  "hasTotalCosts",
  "hasReportingLink",
  "hasHonestCostStatusCopy",
  "hasPortfolioCostSemantics",
];
for (const checkName of requiredPortfolioChecks) {
  if (!guardrails.portfolio?.[checkName]) {
    console.error(
      `/portfolio missing expected Costos y PnL neto marker: ${checkName}`,
    );
    process.exit(1);
  }
}

const requiredExecutionChecks = [
  "hasCostStackOperationalCard",
  "hasReportingLink",
  "hasReadOnlyCopy",
  "hasNoLiveGateCopy",
  "hasMissingEvidenceCopy",
  "hasNoInventedZeroCostStack",
  "hasExecutionCostStackSemantics",
];
for (const checkName of requiredExecutionChecks) {
  if (!guardrails.execution?.[checkName]) {
    console.error(
      `/execution missing expected operational Cost Stack marker: ${checkName}`,
    );
    process.exit(1);
  }
}

const requiredReportingChecks = [
  "hasCostosNav",
  "hasReporting",
  "hasReportingSemantics",
  "hasTaxCommission",
  "hasSpecialCommission",
  "hasPendingCopy",
  "hasCommissionStatusCopy",
];
for (const checkName of requiredReportingChecks) {
  if (!guardrails.reporting?.[checkName]) {
    console.error(
      `/reporting missing expected read-only reporting marker: ${checkName}`,
    );
    process.exit(1);
  }
}
