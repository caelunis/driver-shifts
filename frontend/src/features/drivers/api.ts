import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { get, withQuery } from "../../shared/api/client";
import type { DriverInfo } from "../../shared/api/types";

export function useDrivers(q: string) {
  return useQuery({
    queryKey: ["drivers", q],
    queryFn: () => get<DriverInfo[]>(withQuery("/api/admin/drivers", { q: q.trim() || undefined })),
    placeholderData: keepPreviousData, // no flicker while typing a search
  });
}

export function useDriver(id: number) {
  return useQuery({
    queryKey: ["drivers", "one", id],
    queryFn: () => get<DriverInfo>(`/api/admin/drivers/${id}`),
  });
}
