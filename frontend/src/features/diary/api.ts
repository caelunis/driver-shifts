import { useQuery } from "@tanstack/react-query";

import { get, withQuery } from "@/shared/api/client";
import type { DayInfo, DaySummary, Shift, Trip } from "@/shared/api/types";
import type { DiaryScope } from "@/features/diary/scope";

export function useDays(scope: DiaryScope) {
  return useQuery({
    queryKey: [scope.base, "days"],
    queryFn: () => get<DayInfo[]>(`${scope.base}/days`),
  });
}

/** Summary, shifts and trips of one day. */
export function useDay(scope: DiaryScope, day: string) {
  const summary = useQuery({
    queryKey: [scope.base, "summary", day],
    queryFn: () => get<DaySummary>(withQuery(`${scope.base}/summary`, { work_date: day })),
  });
  const shifts = useQuery({
    queryKey: [scope.base, "shifts", day],
    queryFn: () => get<Shift[]>(withQuery(`${scope.base}/shifts`, { work_date: day })),
  });
  const trips = useQuery({
    queryKey: [scope.base, "trips", day],
    queryFn: () => get<Trip[]>(withQuery(`${scope.base}/trips`, { work_date: day })),
  });
  return { summary, shifts, trips };
}
