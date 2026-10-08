import { useQuery } from "@tanstack/react-query";

import { get } from "@/shared/api/client";
import type { Shift } from "@/shared/api/types";

/** The driver's open shift, or null. */
export function useCurrentShift(enabled = true) {
  return useQuery({
    queryKey: ["current-shift"],
    queryFn: () => get<Shift | null>("/api/shifts/current"),
    enabled,
    // The running duration and "open for over a day" warning follow the clock
    refetchInterval: 60_000,
  });
}

export const WEEK_MS = 7 * 24 * 60 * 60 * 1000;
export const DAY_MS = 24 * 60 * 60 * 1000;

/** A driver may change a shift while it is open or for 7 days after it ended. */
export const isLockedForDriver = (shift: Shift, now = Date.now()) =>
  shift.end != null && now - Date.parse(shift.end) > WEEK_MS;
