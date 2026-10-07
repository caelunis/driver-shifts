// Screenshots for the README, taken from the running stack with the demo data.
//   docker compose up -d --build && node scripts/screenshots.mjs
// A temporary driver with an open shift is created for the shots that need one
// and deleted at the end; the demo accounts are only looked at.
import { chromium, devices, request } from "@playwright/test";
import { mkdir } from "node:fs/promises";

const BASE = process.env.E2E_BASE_URL ?? "http://127.0.0.1:8080";
const OUT = new URL("../../docs/screenshots/", import.meta.url).pathname;
const DEMO_DAY = "2026-10-01";
const PASSWORD = "shots-pass-731";

/** Wall-clock "YYYY-MM-DDTHH:MM" in Almaty (UTC+5), `minutesAgo` before now, on a whole minute. */
function almaty(minutesAgo) {
  const t = new Date(Date.now() - minutesAgo * 60000 + 5 * 3600000);
  return t.toISOString().slice(0, 16);
}

async function api(email, password) {
  const ctx = await request.newContext({ baseURL: BASE });
  const r = await ctx.post("/api/auth/login", { data: { email, password } });
  if (r.status() !== 200) throw new Error(`login ${email}: ${r.status()} ${await r.text()}`);
  return ctx;
}

async function check(response) {
  if (!response.ok()) throw new Error(`${response.url()}: ${response.status()} ${await response.text()}`);
  return response.json();
}

async function login(page, email, password) {
  await page.goto("/login");
  await page.getByLabel("E-mail").fill(email);
  await page.getByLabel("Пароль").fill(password);
  await page.getByRole("button", { name: "Войти" }).click();
  await page.getByRole("button", { name: "Выйти" }).waitFor();
}

async function shot(page, name, opts = {}) {
  await page.waitForLoadState("networkidle");
  await page.screenshot({ path: `${OUT}${name}.png`, ...opts });
  console.log(`  ${name}.png`);
}

await mkdir(OUT, { recursive: true });
const admin = await api("admin@example.com", "admin12345");

// A driver in the middle of a shift: started 3 h ago, two trips so far
const driver = await check(
  await admin.post("/api/admin/drivers", {
    data: {
      email: `asel-${Date.now()}@example.com`,
      password: PASSWORD,
      name: "Асель Нурланова",
      car_model: "Toyota Camry",
      car_plate: `${100 + Math.floor(Math.random() * 900)} KZS 02`,
      default_tz: "Asia/Almaty",
      default_commission_pct: 15,
    },
  }),
);
const asDriver = await api(driver.email, PASSWORD);
const shift = await check(await asDriver.post("/api/shifts", { data: { start: `${almaty(180)}:00+05:00` } }));
for (const [from, to, amount, payment] of [
  [170, 140, 2800, "card"],
  [120, 95, 1900, "cash"],
  [60, 30, 3500, "card"],
]) {
  await check(
    await asDriver.post("/api/trips", {
      data: { shift_id: shift.id, start: `${almaty(from)}:00+05:00`, end: `${almaty(to)}:00+05:00`, amount, payment },
    }),
  );
}
await asDriver.dispose();

const browser = await chromium.launch();
const desktop = { viewport: { width: 1280, height: 820 }, baseURL: BASE, locale: "ru-RU", colorScheme: "light" };
try {
  console.log("Screenshots:");
  let ctx = await browser.newContext(desktop);
  let page = await ctx.newPage();
  await page.goto("/login");
  await shot(page, "login");

  // Driver with sample data: a shift that runs past midnight
  await login(page, "demo@example.com", "demo12345");
  await page.goto(`/day/${DEMO_DAY}`);
  await shot(page, "day");

  // Errors under the fields: one from the browser, the other from the server
  await page.getByRole("button", { name: "+ Поездка" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Окончание").fill("2026-10-02T00:40");
  await dialog.getByLabel("Сумма, ₸").fill("1200");
  await dialog.getByLabel("Комиссия, ₸").fill("1500");
  await dialog.getByRole("button", { name: "Добавить" }).click();
  await dialog.getByLabel("Комиссия, ₸").fill("150");
  await dialog.getByRole("button", { name: "Добавить" }).click();
  await dialog.getByText("Поездка заканчивается после смены").waitFor();
  await shot(page, "validation");
  await ctx.close();

  // Dark theme
  ctx = await browser.newContext({ ...desktop, colorScheme: "dark" });
  page = await ctx.newPage();
  await login(page, "demo@example.com", "demo12345");
  await page.goto(`/day/${DEMO_DAY}`);
  await shot(page, "day-dark");
  await ctx.close();

  // The open shift, on a computer and on a phone
  ctx = await browser.newContext(desktop);
  page = await ctx.newPage();
  await login(page, driver.email, PASSWORD);
  await shot(page, "current-shift");
  await page.goto("/profile");
  await shot(page, "profile");
  await ctx.close();

  ctx = await browser.newContext({ ...devices["iPhone 13"], baseURL: BASE, locale: "ru-RU", colorScheme: "light" });
  page = await ctx.newPage();
  await login(page, driver.email, PASSWORD);
  await shot(page, "mobile", { fullPage: true });
  await ctx.close();

  // Admin
  ctx = await browser.newContext(desktop);
  page = await ctx.newPage();
  await login(page, "admin@example.com", "admin12345");
  await shot(page, "admin-drivers");
  await page.getByRole("link", { name: "Демо-водитель" }).click();
  await page.getByRole("heading", { name: "Демо-водитель" }).waitFor();
  await page.goto(page.url().replace(/day\/.*$/, `day/${DEMO_DAY}`));
  await shot(page, "admin-diary");
  await page.goto("/admin/drivers");
  await page.getByRole("link", { name: "Ерлан Сейтжанов" }).click();
  await page.getByRole("button", { name: "Изменить", exact: true }).click();
  await shot(page, "admin-driver-edit");
  await ctx.close();
} finally {
  await browser.close();
  await admin.delete(`/api/admin/drivers/${driver.id}`);
  await admin.dispose();
}
