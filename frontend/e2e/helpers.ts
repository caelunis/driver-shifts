import { expect, request, type APIRequestContext, type Page } from "@playwright/test";

import { addDays, todayIn } from "@/shared/lib/time";

export const ADMIN = {
  email: process.env.E2E_ADMIN_EMAIL ?? "admin@example.com",
  password: process.env.E2E_ADMIN_PASSWORD ?? "admin12345",
};
export const TZ = "Asia/Almaty";
export const PASSWORD = "e2e-pass-4821";

/** Unique per test run, so runs never collide with each other or with real data. */
export const unique = () => `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;

/** A day a few days back: inside the driver's 7-day window, safely in the past. */
export const pastDay = (n = 2) => addDays(todayIn(TZ), -n);

/** An API session of one account (its own cookie jar). */
export async function apiAs(baseURL: string, email: string, password: string): Promise<APIRequestContext> {
  const ctx = await request.newContext({ baseURL });
  const r = await ctx.post("/api/auth/login", { data: { email, password } });
  expect(r.status(), await r.text()).toBe(200);
  return ctx;
}

export interface TestDriver {
  id: number;
  email: string;
  name: string;
}

/** A fresh driver created through the admin API. */
export async function createDriver(admin: APIRequestContext, extra: Record<string, unknown> = {}): Promise<TestDriver> {
  const tag = unique();
  const body = { email: `e2e-${tag}@example.com`, password: PASSWORD, name: `Тест ${tag}`, default_tz: TZ, ...extra };
  const r = await admin.post("/api/admin/drivers", { data: body });
  expect(r.status(), await r.text()).toBe(201);
  const d = (await r.json()) as TestDriver;
  return { id: d.id, email: body.email, name: body.name };
}

export async function deleteDriver(admin: APIRequestContext, id: number) {
  await admin.delete(`/api/admin/drivers/${id}`);
}

export async function loginUi(page: Page, email: string, password: string) {
  await page.goto("/login");
  await page.getByLabel("E-mail").fill(email);
  await page.getByLabel("Пароль").fill(password);
  await page.getByRole("button", { name: "Войти" }).click();
  // The header switches to the account without a reload
  await expect(page.getByRole("button", { name: "Выйти" })).toBeVisible();
}
