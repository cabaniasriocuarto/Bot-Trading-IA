import { expect, test, type Page } from "@playwright/test";

const username = process.env.PLAYWRIGHT_USERNAME || process.env.ADMIN_USERNAME || "Wadmin";
const password = process.env.PLAYWRIGHT_PASSWORD || process.env.ADMIN_PASSWORD || "moroco123";

async function loginToExecution(page: Page) {
  await page.goto("/login?next=%2Fexecution");
  await expect(page.getByText("Ingreso RTLab Control")).toBeVisible();
  await page.getByPlaceholder("admin o viewer").fill(username);
  await page.getByPlaceholder("********").fill(password);
  await Promise.all([
    page.waitForURL(/\/execution$/, { timeout: 15_000 }),
    page.getByRole("button", { name: "Ingresar" }).click(),
  ]);
  await expect(page.getByText("Trading en Vivo (Paper / Testnet / Live) + Diagnostico")).toBeVisible();
}

test("login y carga de ejecucion operatoria", async ({ page }) => {
  await loginToExecution(page);
  await expect(page.getByRole("heading", { name: "Checklist Live Ready" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Preflight LIVE Final" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Reconciliation" })).toBeVisible();
});

test("expone controles operatorios sin ejecutar side effects", async ({ page }) => {
  await loginToExecution(page);
  await expect(page.getByRole("button", { name: /^Refrescar panel$/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /^Modo seguro ON$/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /^Cerrar posiciones$/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /^Kill switch$/ })).toBeVisible();
});

test("permite navegar a alertas y logs como flujo de consulta", async ({ page }) => {
  await loginToExecution(page);
  await page.getByRole("link", { name: "Alertas y Logs" }).click();
  await expect(page).toHaveURL(/\/alerts$/);
  await expect(page.getByRole("heading", { name: "Alertas y Logs" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Aplicar filtros" })).toBeVisible();
});
