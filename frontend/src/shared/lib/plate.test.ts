import { describe, expect, it } from "vitest";

import { carText, formatPlate, normalizePlate } from "@/shared/lib/plate";

describe("normalizePlate", () => {
  it.each([
    ["123 ABC 02", "123ABC02"],
    ["123abc02", "123ABC02"],
    ["123-AB-17", "123AB17"],
    ["777 ААА 02", "777AAA02"], // Cyrillic А typed on a Russian keyboard
    ["123 АВС 20", "123ABC20"],
  ])("%s -> %s", (input, expected) => {
    expect(normalizePlate(input)).toBe(expected);
  });

  it.each(["A123BC", "123ABC21", "123ABC00", "12ABC02", "123ABCD02", "123 ЖЖЖ 02", ""])(
    "rejects %j",
    (input) => {
      expect(normalizePlate(input)).toBeNull();
    },
  );
});

describe("display", () => {
  it("adds spaces back", () => {
    expect(formatPlate("777AAA02")).toBe("777 AAA 02");
    expect(formatPlate(null)).toBe("");
  });

  it("joins model and plate, skipping what is missing", () => {
    expect(carText({ car_model: "Hyundai Accent", car_plate: "777AAA02" })).toBe("Hyundai Accent, 777 AAA 02");
    expect(carText({ car_model: "", car_plate: "777AAA02" })).toBe("777 AAA 02");
    expect(carText({ car_model: null, car_plate: null })).toBe("");
  });
});
