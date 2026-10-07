import { formatOffset, offsetMinutes } from "./time";

export const DEFAULT_TZ = "Asia/Almaty";

/** Kazakhstan's zones go first in the select; the rest follow alphabetically. */
export const KZ_ZONES = [
  "Asia/Almaty",
  "Asia/Aqtau",
  "Asia/Aqtobe",
  "Asia/Atyrau",
  "Asia/Oral",
  "Asia/Qostanay",
  "Asia/Qyzylorda",
];

export function allZones(): string[] {
  const list = typeof Intl.supportedValuesOf === "function" ? Intl.supportedValuesOf("timeZone") : [];
  return list.filter((z) => !KZ_ZONES.includes(z));
}

/** "Asia/Almaty (UTC+05:00)" */
export function zoneLabel(tz: string, now = new Date()): string {
  try {
    return `${tz.replace(/_/g, " ")} (UTC${formatOffset(offsetMinutes(tz, now))})`;
  } catch {
    return tz;
  }
}
