import { expect, test, type APIRequestContext } from "@playwright/test";

import { formatDay } from "@/shared/lib/time";
import { ADMIN, apiAs, createDriver, deleteDriver, loginUi, PASSWORD, pastDay, type TestDriver } from "@e2e/helpers";

// One driver per test file, used by its tests in order: they build on each other
test.describe.configure({ mode: "serial" });

let admin: APIRequestContext;
let driver: TestDriver;

test.beforeAll(async ({ baseURL }) => {
  admin = await apiAs(baseURL!, ADMIN.email, ADMIN.password);
  driver = await createDriver(admin); // no commission percent: the driver enters it
});

test.afterAll(async () => {
  await deleteDriver(admin, driver.id);
  await admin.dispose();
});

test.beforeEach(async ({ page }) => {
  await loginUi(page, driver.email, PASSWORD);
});

const day = pastDay();
const shiftCard = (page: import("@playwright/test").Page) => page.getByRole("article", { name: "Смена 08:00" });

test("enters a past shift and lands on its day", async ({ page }) => {
  await expect(page.getByText("Смена не начата")).toBeVisible();
  await page.getByRole("button", { name: "Внести прошедшую" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Начало").fill(`${day}T08:00`);
  await dialog.getByLabel("Окончание").fill(`${day}T12:00`);
  await dialog.getByLabel("Заметка").fill("e2e");
  await dialog.getByRole("button", { name: "Добавить" }).click();

  await expect(page.getByText("Смена добавлена")).toBeVisible();
  await expect(page).toHaveURL(new RegExp(`/day/${day}$`));
  await expect(page.getByRole("heading", { name: formatDay(day) })).toBeVisible();
  await expect(shiftCard(page).getByRole("heading", { name: "08:00 – 12:00" })).toBeVisible();
});

test("adds a trip; the form checks itself and the server", async ({ page }) => {
  await page.goto(`/day/${day}`);
  await shiftCard(page).getByRole("button", { name: "+ Поездка" }).click();
  const dialog = page.getByRole("dialog");
  // The start is prefilled with the shift's start
  await expect(dialog.getByLabel("Начало")).toHaveValue(`${day}T08:00`);

  // Checked in the browser: no request is sent
  await dialog.getByLabel("Окончание").fill(`${day}T07:50`);
  await dialog.getByRole("button", { name: "Добавить" }).click();
  await expect(dialog.getByText("Окончание должно быть позже начала")).toBeVisible();
  await expect(dialog.getByText("Укажите сумму")).toBeVisible();

  // Checked by the server: the trip runs past the end of the shift
  await dialog.getByLabel("Окончание").fill(`${day}T12:30`);
  await dialog.getByLabel("Сумма, ₸").fill("2500");
  await dialog.getByLabel("Комиссия, ₸").fill("300");
  await dialog.getByRole("button", { name: "Добавить" }).click();
  await expect(dialog.getByText("Поездка заканчивается после смены")).toBeVisible();

  await dialog.getByLabel("Окончание").fill(`${day}T08:25`);
  await dialog.getByRole("button", { name: "Добавить" }).click();
  await expect(page.getByText("Поездка добавлена")).toBeVisible();
  await expect(dialog).toBeHidden();
  await expect(shiftCard(page).getByRole("cell", { name: "2 200 ₸" })).toBeVisible();
});

test("edits the trip; totals follow", async ({ page }) => {
  await page.goto(`/day/${day}`);
  await shiftCard(page).getByRole("button", { name: "Изменить поездку" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByLabel("Сумма, ₸")).toHaveValue("2500");
  await dialog.getByLabel("Сумма, ₸").fill("3000");
  await dialog.getByRole("button", { name: "Сохранить" }).click();

  await expect(page.getByText("Поездка изменена")).toBeVisible();
  await expect(shiftCard(page).getByRole("cell", { name: "2 700 ₸" })).toBeVisible();
  await expect(page.locator(".stat.main")).toContainText("2 700 ₸");
});

test("deletes the trip after confirmation", async ({ page }) => {
  await page.goto(`/day/${day}`);
  await shiftCard(page).getByRole("button", { name: "Удалить поездку" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Удалить" }).click();
  await expect(page.getByText("Поездка удалена")).toBeVisible();
  await expect(shiftCard(page).getByText("Поездок пока нет")).toBeVisible();
});

test("starts a shift now and closes it", async ({ page }) => {
  await page.getByRole("button", { name: "Начать смену" }).click();
  await expect(page.getByText("Смена началась")).toBeVisible();
  const bar = page.getByRole("region", { name: "Текущая смена" });
  await expect(bar.getByText("Смена идёт")).toBeVisible();

  await bar.getByRole("button", { name: "Закончить смену" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Окончание").fill(""); // empty: the server takes "now"
  await dialog.getByRole("button", { name: "Закончить" }).click();
  await expect(page.getByText("Смена закончена")).toBeVisible();
  await expect(bar.getByText("Смена не начата")).toBeVisible();
});

test("a shift that is still open cannot be started twice", async ({ page }) => {
  await page.getByRole("button", { name: "Начать смену" }).click();
  await expect(page.getByText("Смена идёт")).toBeVisible();
  // Another tab starts a shift meanwhile: the server refuses, the page explains
  const r = await page.request.post("/api/shifts", { data: {} });
  expect(r.status()).toBe(409);
  expect((await r.json()).error.code).toBe("shift_already_open");
});
