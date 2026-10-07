import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";

import { api, ApiError, get } from "../../shared/api/client";
import type { Profile } from "../../shared/api/types";

export const meKey = ["me"] as const;

/**
 * Switch the cached account. Everything else cached belonged to the previous account
 * and is dropped. The profile query itself is updated, not removed: mounted components
 * (the header) observe it and would not notice a query created anew.
 */
function switchAccount(qc: QueryClient, profile: Profile | null) {
  qc.removeQueries({ predicate: (q) => q.queryKey[0] !== meKey[0] });
  qc.setQueryData(meKey, profile);
}

/** The logged-in account, or null when there is no session. */
export function useMe() {
  return useQuery({
    queryKey: meKey,
    queryFn: async () => {
      try {
        return await get<Profile>("/api/me");
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) return null;
        throw e;
      }
    },
    staleTime: 60_000,
  });
}

export function useLogin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { email: string; password: string }) => api<Profile>("POST", "/api/auth/login", body),
    onSuccess: (profile) => switchAccount(qc, profile),
  });
}

export function useLogout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api<void>("POST", "/api/auth/logout", {}),
    onSettled: () => switchAccount(qc, null),
  });
}
