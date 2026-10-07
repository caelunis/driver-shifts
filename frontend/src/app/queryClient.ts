import { MutationCache, QueryCache, QueryClient } from "@tanstack/react-query";

import { meKey } from "../features/auth/api";
import { ApiError } from "../shared/api/client";

// Any 401 means the session is gone (expired, or ended by a password change):
// forgetting the profile sends the user to the login screen.
function onError(err: unknown) {
  if (err instanceof ApiError && err.status === 401 && err.code === "not_authenticated") {
    queryClient.setQueryData(meKey, null);
  }
}

export const queryClient = new QueryClient({
  queryCache: new QueryCache({ onError }),
  mutationCache: new MutationCache({ onError }),
  defaultOptions: {
    queries: {
      // Client errors will not fix themselves on retry
      retry: (count, err) => !(err instanceof ApiError && err.status >= 400 && err.status < 500) && count < 2,
      refetchOnWindowFocus: true,
    },
  },
});
