import { describe, expect, it } from "vitest";

import { commissionFor, formatMoney, formatPct } from "./money";
import { plural, tripsText } from "./plural";

describe("commissionFor", () => {
  // Same cases as the server's tests (backend tests/unit/test_commission_formula.py)
  it.each([
    [2400, 15, 360],
    [2350, 15, 353], // 352.5 rounds half up, not to even
    [1000, 12.5, 125],
    [999, 12.5, 125], // 124.875
    [1, 50, 1], // 0.5 rounds up
    [100, 0, 0],
    [3333, 33.33, 1111], // 1110.89
  ])("%i ₸ at %f%% = %i ₸", (amount, pct, expected) => {
    expect(commissionFor(amount, pct)).toBe(expected);
  });
});

describe("formatting", () => {
  it("money and percent in Russian", () => {
    expect(formatMoney(12345).replace(/\s/g, " ")).toBe("12 345 ₸");
    expect(formatPct(12.5)).toBe("12,5%");
    expect(formatPct(15)).toBe("15%");
  });

  it("plural forms", () => {
    expect([1, 2, 5, 11, 21, 22, 25, 112].map(tripsText)).toEqual([
      "1 поездка", "2 поездки", "5 поездок", "11 поездок",
      "21 поездка", "22 поездки", "25 поездок", "112 поездок",
    ]);
    expect(plural(14, "a", "b", "c")).toBe("c");
  });
});
