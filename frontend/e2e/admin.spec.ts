import { expect, test, type APIRequestContext } from "@playwright/test";

import { ADMIN, apiAs, createDriver, deleteDriver, loginUi, PASSWORD, pastDay, unique } from "./helpers";

let admin: APIRequestContext;
const cleanup: number[] = [];

test.beforeAll(async ({ baseURL }) => {
  admin = await apiAs(baseURL!, ADMIN.email, ADMIN.password);
});

test.afterAll(async () => {
  for (const id of cleanup) await deleteDriver(admin, id);
  await admin.dispose();
});

test.beforeEach(async ({ page }) => {
  await loginUi(page, ADMIN.email, ADMIN.password);
});

test("creates a driver; server-side rules show under the fields", async ({ page }) => {
  const tag = unique();
  const letters = Array.from({ length: 3 }, () => String.fromCharCode(65 + Math.floor(Math.random() * 26))).join("");
  const plate = `${100 + Math.floor(Math.random() * 900)} ${letters} 02`;
  await page.getByRole("button", { name: "+ Водитель" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("E-mail").fill(`e2e-${tag}@example.com`);
  await dialog.getByLabel("Временный пароль").fill("qwerty123"); // on the server's common list
  await dialog.getByLabel("Имя").fill(`Айдар ${tag}`);
  await dialog.getByLabel("Автомобиль").fill("Kia Rio");
  await dialog.getByLabel("Госномер").fill(plate.toLowerCase());
  await dialog.getByLabel("Комиссия, %").fill("15");
  await dialog.getByRole("button", { name: "Создать" }).click();
  await expect(dialog.getByText("Слишком простой пароль")).toBeVisible();

  await dialog.getByLabel("Временный пароль").fill(PASSWORD);
  await dialog.getByRole("button", { name: "Создать" }).click();
  await expect(page.getByText(`Водитель Айдар ${tag} добавлен`)).toBeVisible();
  await expect(page.getByRole("heading", { name: `Айдар ${tag}` })).toBeVisible();
  await expect(page.getByText(`Kia Rio, ${plate.toUpperCase()}`)).toBeVisible();
  cleanup.push(Number(page.url().match(/drivers\/(\d+)/)![1]));
});

test("a taken email is reported under the email field", async ({ page }) => {
  const existing = await createDriver(admin);
  cleanup.push(existing.id);
  await page.getByRole("button", { name: "+ Водитель" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("E-mail").fill(existing.email.toUpperCase());
  await dialog.getByLabel("Временный пароль").fill(PASSWORD);
  await dialog.getByLabel("Имя").fill("Дубль");
  await dialog.getByRole("button", { name: "Создать" }).click();
  await expect(dialog.getByText("Этот e-mail уже зарегистрирован")).toBeVisible();
});

test("corrects a driver's trip and deletes the driver", async ({ page, baseURL }) => {
  // The driver's own data, entered through the API as the driver would
  const d = await createDriver(admin, { default_commission_pct: 15 });
  const day = pastDay(3);
  const asDriver = await apiAs(baseURL!, d.email, PASSWORD);
  const shift = await (
    await asDriver.post("/api/shifts", { data: { start: `${day}T09:00:00+05:00`, end: `${day}T13:00:00+05:00` } })
  ).json();
  const trip = await asDriver.post("/api/trips", {
    data: { shift_id: shift.id, start: `${day}T09:10:00+05:00`, end: `${day}T09:40:00+05:00`, amount: 2000, payment: "cash" },
  });
  expect(trip.status()).toBe(201);
  await asDriver.dispose();

  await page.getByRole("searchbox", { name: "Поиск водителей" }).fill(d.email);
  await page.getByRole("link", { name: d.name }).click();
  await expect(page.getByRole("heading", { name: d.name })).toBeVisible();
  // Opens on the driver's last day with a shift
  await expect(page.getByRole("cell", { name: "1 700 ₸" })).toBeVisible();

  await page.getByRole("button", { name: "Изменить поездку" }).click();
  const dialog = page.getByRole("dialog");
  // The percent stored with the trip drives the commission preview
  await dialog.getByLabel("Сумма, ₸").fill("3000");
  await expect(dialog.getByText("15% от суммы = 450 ₸")).toBeVisible();
  await dialog.getByRole("button", { name: "Сохранить" }).click();
  await expect(page.getByRole("cell", { name: "2 550 ₸" })).toBeVisible();
  // The admin does not add trips: no such button in the driver's diary
  await expect(page.getByRole("button", { name: "+ Поездка" })).toHaveCount(0);

  await page.getByRole("button", { name: "Удалить", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Удалить" }).click();
  await expect(page.getByText("Водитель удалён")).toBeVisible();
  await expect(page).toHaveURL(/\/admin\/drivers$/);
});

test("a driver cannot open admin pages", async ({ page, baseURL }) => {
  const d = await createDriver(admin);
  cleanup.push(d.id);
  await page.getByRole("button", { name: "Выйти" }).click();
  await loginUi(page, d.email, PASSWORD);
  await page.goto("/admin/drivers");
  await expect(page).toHaveURL(/\/day\//); // sent back to the diary
  const r = await (await apiAs(baseURL!, d.email, PASSWORD)).get("/api/admin/drivers");
  expect(r.status()).toBe(403);
});
