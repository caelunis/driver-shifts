import type { QueryClient } from "@tanstack/react-query";

import { API_V1 } from "@/shared/api/client";

/**
 * Whose diary is shown and by whom. The driver's endpoints live under /api/v1, the
 * admin's copies of them under /api/v1/admin/drivers/{id}, with the same paths below.
 */
export interface DiaryScope {
  base: string;
  role: "driver" | "admin";
  /** The driver's IANA zone: new times are entered in it */
  tz: string;
  /** Commission percent from the driver's profile; null: the driver enters it */
  commissionPct: number | null;
  /** Link to a day of this diary */
  dayPath: (day: string) => string;
}

export const driverScope = (tz: string, commissionPct: number | null): DiaryScope => ({
  base: API_V1,
  role: "driver",
  tz,
  commissionPct,
  dayPath: (day) => `/day/${day}`,
});

export const adminScope = (driverId: string, tz: string, commissionPct: number | null): DiaryScope => ({
  base: `${API_V1}/admin/drivers/${driverId}`,
  role: "admin",
  tz,
  commissionPct,
  dayPath: (day) => `/admin/drivers/${driverId}/day/${day}`,
});

/** After any change: everything of this diary, the open shift and the admin's totals. */
export function invalidateDiary(qc: QueryClient, scope: DiaryScope) {
  return Promise.all([
    qc.invalidateQueries({ queryKey: [scope.base] }),
    qc.invalidateQueries({ queryKey: ["current-shift"] }),
    qc.invalidateQueries({ queryKey: ["drivers"] }),
  ]);
}
