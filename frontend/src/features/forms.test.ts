import { describe, expect, it } from "vitest";

import { driverFormSchema } from "@/features/drivers/schema";
import { shiftFormSchema } from "@/features/shifts/schema";
import { tripFormSchema } from "@/features/trips/schema";

/** {field: message} of a failed parse; like the form, the first message of each field */
function errors(result: { success: boolean; error?: { issues: { path: PropertyKey[]; message: string }[] } }) {
  const out: Record<string, string> = {};
  for (const i of result.error?.issues ?? []) out[String(i.path[0])] ??= i.message;
  return out;
}

const trip = { start: "2026-10-01T08:10", end: "2026-10-01T08:32", amount: "2400", payment: "card" as const, commission: "360" };

describe("trip form", () => {
  it("accepts a normal trip", () => {
    expect(tripFormSchema(true).safeParse(trip).success).toBe(true);
  });

  it.each([
    [{ end: "2026-10-01T08:00" }, "end", "Окончание должно быть позже начала"],
    [{ end: "2026-10-01T14:11" }, "end", "Поездка длится не больше 6 часов"],
    [{ amount: "0" }, "amount", "Сумма должна быть больше 0"],
    [{ amount: "500001" }, "amount", "Не больше 500 000 ₸"],
    [{ amount: "12.5" }, "amount", "Введите сумму целым числом"],
    [{ commission: "2400" }, "commission", "Комиссия должна быть меньше суммы"],
    [{ commission: "" }, "commission", "Укажите комиссию"],
    [{ commission: "1.5" }, "commission", "Введите комиссию целым числом"],
    [{ amount: "" }, "amount", "Укажите сумму"],
  ])("rejects %j", (patch, fieldName, message) => {
    expect(errors(tripFormSchema(true).safeParse({ ...trip, ...patch }))[fieldName]).toBe(message);
  });

  it("does not ask for a commission the server computes", () => {
    expect(tripFormSchema(false).safeParse({ ...trip, commission: "" }).success).toBe(true);
  });
});

describe("shift form", () => {
  const shift = { start: "2026-10-01T08:00", end: "2026-10-01T18:00", note: "" };

  it("a past shift needs both ends, an edit only the start", () => {
    expect(errors(shiftFormSchema("past").safeParse({ ...shift, end: "" }))).toEqual({ end: "Укажите окончание" });
    expect(shiftFormSchema("edit").safeParse({ ...shift, end: "" }).success).toBe(true);
    expect(shiftFormSchema("close").safeParse({ start: "", end: "", note: "" }).success).toBe(true);
  });

  it("at most 24 hours", () => {
    expect(errors(shiftFormSchema("past").safeParse({ ...shift, end: "2026-10-02T08:01" })).end).toBe(
      "Смена длится не больше 24 часов",
    );
  });
});

describe("driver form", () => {
  const driver = {
    email: "erlan@example.com",
    password: "temp-pass-1",
    name: "Ерлан",
    car_model: "Hyundai Accent",
    car_plate: "777 aaa 02",
    default_tz: "Asia/Almaty",
    default_commission_pct: "12,5",
  };

  it("accepts a valid driver", () => {
    expect(driverFormSchema(true).safeParse(driver).success).toBe(true);
  });

  it.each([
    [{ email: "nope" }, "email"],
    [{ password: "short" }, "password"],
    [{ password: "onlyletters" }, "password"],
    [{ password: "1234567890" }, "password"],
    [{ name: "   " }, "name"],
    [{ name: "12345" }, "name"],
    [{ car_plate: "A123BC" }, "car_plate"],
    [{ default_commission_pct: "100" }, "default_commission_pct"],
  ])("rejects %j", (patch, fieldName) => {
    expect(Object.keys(errors(driverFormSchema(true).safeParse({ ...driver, ...patch })))).toEqual([fieldName]);
  });

  it("an empty password keeps the old one when editing", () => {
    expect(driverFormSchema(false).safeParse({ ...driver, email: "", password: "" }).success).toBe(true);
    expect(driverFormSchema(true).safeParse({ ...driver, password: "" }).success).toBe(false);
  });
});
