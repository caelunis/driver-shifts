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

const trip = { started_at: "2026-10-01T08:10", ended_at: "2026-10-01T08:32", fare: "2400", payment_method: "card" as const, commission_amount: "360" };

describe("trip form", () => {
  it("accepts a normal trip", () => {
    expect(tripFormSchema(true).safeParse(trip).success).toBe(true);
  });

  it.each([
    [{ ended_at: "2026-10-01T08:00" }, "ended_at", "Окончание должно быть позже начала"],
    [{ ended_at: "2026-10-01T14:11" }, "ended_at", "Поездка длится не больше 6 часов"],
    [{ fare: "0" }, "fare", "Сумма должна быть больше 0"],
    [{ fare: "500001" }, "fare", "Не больше 500 000 ₸"],
    [{ fare: "12.5" }, "fare", "Введите сумму целым числом"],
    [{ commission_amount: "2400" }, "commission_amount", "Комиссия должна быть меньше суммы"],
    [{ commission_amount: "" }, "commission_amount", "Укажите комиссию"],
    [{ commission_amount: "1.5" }, "commission_amount", "Введите комиссию целым числом"],
    [{ fare: "" }, "fare", "Укажите сумму"],
  ])("rejects %j", (patch, fieldName, message) => {
    expect(errors(tripFormSchema(true).safeParse({ ...trip, ...patch }))[fieldName]).toBe(message);
  });

  it("does not ask for a commission the server computes", () => {
    expect(tripFormSchema(false).safeParse({ ...trip, commission_amount: "" }).success).toBe(true);
  });
});

describe("shift form", () => {
  const shift = { started_at: "2026-10-01T08:00", ended_at: "2026-10-01T18:00", note: "" };

  it("a past shift needs both ends, an edit only the start", () => {
    expect(errors(shiftFormSchema("past").safeParse({ ...shift, ended_at: "" }))).toEqual({ ended_at: "Укажите окончание" });
    expect(shiftFormSchema("edit").safeParse({ ...shift, ended_at: "" }).success).toBe(true);
    expect(shiftFormSchema("close").safeParse({ started_at: "", ended_at: "", note: "" }).success).toBe(true);
  });

  it("at most 24 hours", () => {
    expect(errors(shiftFormSchema("past").safeParse({ ...shift, ended_at: "2026-10-02T08:01" })).ended_at).toBe(
      "Смена длится не больше 24 часов",
    );
  });
});

describe("driver form", () => {
  const driver = {
    email: "erlan@example.com",
    password: "temp-pass-1",
    full_name: "Ерлан",
    car_model: "Hyundai Accent",
    car_plate: "777 aaa 02",
    timezone: "Asia/Almaty",
    commission_percent: "12,5",
  };

  it("accepts a valid driver", () => {
    expect(driverFormSchema(true).safeParse(driver).success).toBe(true);
  });

  it.each([
    [{ email: "nope" }, "email"],
    [{ password: "short" }, "password"],
    [{ password: "onlyletters" }, "password"],
    [{ password: "1234567890" }, "password"],
    [{ full_name: "   " }, "full_name"],
    [{ full_name: "12345" }, "full_name"],
    [{ car_plate: "A123BC" }, "car_plate"],
    [{ commission_percent: "100" }, "commission_percent"],
  ])("rejects %j", (patch, fieldName) => {
    expect(Object.keys(errors(driverFormSchema(true).safeParse({ ...driver, ...patch })))).toEqual([fieldName]);
  });

  it("an empty password keeps the old one when editing", () => {
    expect(driverFormSchema(false).safeParse({ ...driver, email: "", password: "" }).success).toBe(true);
    expect(driverFormSchema(true).safeParse({ ...driver, password: "" }).success).toBe(false);
  });
});
