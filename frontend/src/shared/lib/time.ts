// Dates and times. The server sends every time with the UTC offset it was entered in,
// so a time is displayed by its own wall-clock part, not converted to the browser's zone.
// New times are entered in the driver's IANA zone and sent with that zone's offset.

const pad = (n: number) => String(n).padStart(2, "0");

/** Minutes east of UTC that `tz` has at the instant `at`. */
export function offsetMinutes(tz: string, at: Date): number {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: tz,
    hourCycle: "h23",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).formatToParts(at);
  const v = (type: string) => Number(parts.find((p) => p.type === type)?.value);
  const wall = Date.UTC(v("year"), v("month") - 1, v("day"), v("hour"), v("minute"), v("second"));
  return Math.round((wall - Math.floor(at.getTime() / 1000) * 1000) / 60000);
}

/** 300 -> "+05:00" */
export function formatOffset(minutes: number): string {
  const sign = minutes < 0 ? "-" : "+";
  const a = Math.abs(minutes);
  return `${sign}${pad(Math.floor(a / 60))}:${pad(a % 60)}`;
}

/** "+05:00" -> 300; null for an ISO string without an offset. */
export function parseOffset(iso: string): number | null {
  if (iso.endsWith("Z")) return 0;
  const m = /([+-])(\d{2}):(\d{2})$/.exec(iso);
  if (!m) return null;
  return (m[1] === "-" ? -1 : 1) * (Number(m[2]) * 60 + Number(m[3]));
}

/**
 * Wall-clock time from a datetime-local input ("2026-10-01T08:10") in zone `tz` ->
 * ISO with the offset the zone has at that moment ("2026-10-01T08:10:00+05:00").
 * Around a DST change the offset is re-checked at the resulting instant.
 */
export function localToIso(local: string, tz: string): string {
  const [d, t] = local.split("T") as [string, string];
  const [y, mo, da] = d.split("-").map(Number) as [number, number, number];
  const [h, mi] = t.split(":").map(Number) as [number, number];
  const asUtc = Date.UTC(y, mo - 1, da, h, mi);
  let off = offsetMinutes(tz, new Date(asUtc));
  off = offsetMinutes(tz, new Date(asUtc - off * 60000));
  return `${d}T${pad(h)}:${pad(mi)}:00${formatOffset(off)}`;
}

/** Same as localToIso, but with a fixed offset (keeps the offset of an edited time). */
export function localWithOffset(local: string, offsetMin: number): string {
  return `${local.slice(0, 16)}:00${formatOffset(offsetMin)}`;
}

/** ISO from the server -> value for a datetime-local input, in the time's own offset. */
export const isoToLocal = (iso: string) => iso.slice(0, 16);

/** "08:10" of an ISO time, in its own offset. */
export const hhmm = (iso: string) => iso.slice(11, 16);

/** Wall-clock "now" in `tz`, for datetime-local inputs. */
export function nowLocal(tz: string, now = new Date()): string {
  const shifted = new Date(now.getTime() + offsetMinutes(tz, now) * 60000);
  return shifted.toISOString().slice(0, 16);
}

/** Today's date in `tz`, "YYYY-MM-DD". */
export const todayIn = (tz: string, now = new Date()) => nowLocal(tz, now).slice(0, 10);

/** Date part of an ISO time, in its own offset. */
export const isoDay = (iso: string) => iso.slice(0, 10);

const DAY_TITLE = new Intl.DateTimeFormat("ru-RU", {
  day: "numeric",
  month: "long",
  weekday: "short",
  timeZone: "UTC",
});
const SHORT_DAY = new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "short", timeZone: "UTC" });

const dayAsUtc = (day: string) => new Date(`${day}T00:00:00Z`);

/** "2026-10-01" -> "1 октября, чт" */
export const formatDay = (day: string) => DAY_TITLE.format(dayAsUtc(day));

/** ISO -> "1 окт., 08:10" in the time's own offset */
export function formatDateTime(iso: string): string {
  return `${SHORT_DAY.format(dayAsUtc(isoDay(iso)))}, ${hhmm(iso)}`;
}

/** 200 -> "3 ч 20 мин" */
export function formatDuration(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = Math.round(minutes % 60);
  if (h === 0) return `${m} мин`;
  return m === 0 ? `${h} ч` : `${h} ч ${m} мин`;
}

export function addDays(day: string, n: number): string {
  const d = dayAsUtc(day);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

/** Minutes between two ISO times (or an ISO time and now). */
export const minutesBetween = (from: string, to: string | Date) =>
  ((to instanceof Date ? to.getTime() : Date.parse(to)) - Date.parse(from)) / 60000;

/**
 * Like isoToLocal, but rounded up to a whole minute: a datetime-local input has minute
 * precision, and a trip may not start before a shift that started at 08:00:30.
 */
export function isoToLocalCeil(iso: string): string {
  const local = isoToLocal(iso);
  const rest = iso.slice(16).replace(/([+-]\d{2}:\d{2}|Z)$/, ""); // ":30.123" or ""
  if (!/[1-9]/.test(rest)) return local;
  const wall = Date.parse(`${local}:00Z`) + 60000;
  return new Date(wall).toISOString().slice(0, 16);
}
