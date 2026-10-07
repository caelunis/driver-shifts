import { afterEach, describe, expect, it, vi } from "vitest";

import { api, ApiError } from "./client";
import { errorMessage, fieldErrorMessage } from "./errors";

const field = (code: string, ctx: Record<string, unknown> = {}, name = "amount") => ({
  field: name,
  code,
  message: "English fallback",
  ctx,
});

describe("fieldErrorMessage", () => {
  it("translates codes, using ctx", () => {
    expect(fieldErrorMessage(field("greater_than", { gt: 0 }))).toBe("Должно быть больше 0");
    expect(fieldErrorMessage(field("commission_fixed", { expected: 360 })).replace(/\s/g, " ")).toBe(
      "Комиссию считает сервер: 360 ₸",
    );
    expect(fieldErrorMessage(field("outside_shift", {}, "start"))).toBe("Поездка начинается раньше смены");
    expect(fieldErrorMessage(field("outside_shift", {}, "end"))).toBe("Поездка заканчивается после смены");
  });

  it("falls back to the server's message for unknown codes", () => {
    expect(fieldErrorMessage(field("brand_new_rule"))).toBe("English fallback");
  });
});

describe("errorMessage", () => {
  it("maps conflict codes", () => {
    expect(errorMessage(new ApiError(409, { code: "shift_locked" }))).toMatch(/больше 7 дней/);
    expect(errorMessage(new ApiError(409, { code: "trip_overlap" }))).toBe("Пересекается с другой поездкой");
  });

  it("explains network and server failures", () => {
    expect(errorMessage(new ApiError(0))).toMatch(/Сервер недоступен/);
    expect(errorMessage(new ApiError(502))).toBe("Ошибка сервера (502)");
    expect(errorMessage(new Error("boom"))).toBe("Что-то пошло не так");
  });
});

describe("api client", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("turns the error envelope into an ApiError", async () => {
    const body = {
      error: { code: "validation_error", message: "Some fields are invalid", ctx: {}, fields: [field("missing")] },
    };
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status: 422 })));
    const err = await api("POST", "/api/trips", {}).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 422, code: "validation_error", fields: [{ field: "amount", code: "missing" }] });
  });

  it("sends JSON with the right content type", async () => {
    const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) => new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    await api("POST", "/api/auth/logout", {});
    const init = fetchMock.mock.calls[0]![1]!;
    expect(init.headers).toEqual({ "Content-Type": "application/json" });
    expect(init.body).toBe("{}");
  });

  it("reports a network failure as status 0", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("Failed to fetch"))));
    await expect(api("GET", "/api/me")).rejects.toMatchObject({ status: 0, code: "network_error" });
  });
});
