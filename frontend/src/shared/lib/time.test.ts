import { describe, expect, it } from "vitest";

import {
  addDays,
  formatDuration,
  formatOffset,
  isoToLocalCeil,
  localToIso,
  localWithOffset,
  nowLocal,
  offsetMinutes,
  parseOffset,
  todayIn,
} from "./time";

describe("offsets", () => {
  it("knows Almaty is UTC+5 since 2024", () => {
    expect(offsetMinutes("Asia/Almaty", new Date("2026-10-01T00:00:00Z"))).toBe(300);
  });

  it("follows daylight saving time", () => {
    expect(offsetMinutes("Europe/Berlin", new Date("2026-07-01T12:00:00Z"))).toBe(120);
    expect(offsetMinutes("Europe/Berlin", new Date("2026-12-01T12:00:00Z"))).toBe(60);
  });

  it("formats and parses", () => {
    expect(formatOffset(300)).toBe("+05:00");
    expect(formatOffset(-210)).toBe("-03:30");
    expect(formatOffset(0)).toBe("+00:00");
    expect(parseOffset("2026-10-01T08:10:00+05:00")).toBe(300);
    expect(parseOffset("2026-10-01T08:10:00-03:30")).toBe(-210);
    expect(parseOffset("2026-10-01T08:10:00Z")).toBe(0);
    expect(parseOffset("2026-10-01T08:10:00")).toBeNull();
  });
});

describe("localToIso", () => {
  it("adds the zone's offset to a wall-clock time", () => {
    expect(localToIso("2026-10-01T08:10", "Asia/Almaty")).toBe("2026-10-01T08:10:00+05:00");
  });

  it("uses the offset valid on that date, not today's", () => {
    expect(localToIso("2026-07-01T08:10", "Europe/Berlin")).toBe("2026-07-01T08:10:00+02:00");
    expect(localToIso("2026-12-01T08:10", "Europe/Berlin")).toBe("2026-12-01T08:10:00+01:00");
  });

  it("keeps the given offset when editing", () => {
    expect(localWithOffset("2026-10-01T09:00", 360)).toBe("2026-10-01T09:00:00+06:00");
  });
});

describe("now and today in a zone", () => {
  const instant = new Date("2026-10-01T20:30:00Z"); // 01:30 next day in Almaty

  it("gives the wall clock of the zone, not of the browser", () => {
    expect(nowLocal("Asia/Almaty", instant)).toBe("2026-10-02T01:30");
    expect(todayIn("Asia/Almaty", instant)).toBe("2026-10-02");
    expect(todayIn("UTC", instant)).toBe("2026-10-01");
  });
});

describe("isoToLocalCeil", () => {
  it("rounds seconds up so a trip cannot start before its shift", () => {
    expect(isoToLocalCeil("2026-10-01T08:00:30+05:00")).toBe("2026-10-01T08:01");
    expect(isoToLocalCeil("2026-10-01T08:00:00.250+05:00")).toBe("2026-10-01T08:01");
    expect(isoToLocalCeil("2026-10-01T23:59:01+05:00")).toBe("2026-10-02T00:00");
  });

  it("leaves whole minutes alone", () => {
    expect(isoToLocalCeil("2026-10-01T08:00:00+05:00")).toBe("2026-10-01T08:00");
    expect(isoToLocalCeil("2026-10-01T08:00+05:00")).toBe("2026-10-01T08:00");
  });
});

describe("formatting", () => {
  it("durations", () => {
    expect(formatDuration(45)).toBe("45 мин");
    expect(formatDuration(120)).toBe("2 ч");
    expect(formatDuration(200)).toBe("3 ч 20 мин");
  });

  it("day arithmetic across months", () => {
    expect(addDays("2026-10-31", 1)).toBe("2026-11-01");
    expect(addDays("2026-03-01", -1)).toBe("2026-02-28");
  });
});
