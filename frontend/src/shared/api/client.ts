import type { ErrorBody, FieldError } from "@/shared/api/types";

/** A non-2xx response, or no response at all (status 0). */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly fields: FieldError[];
  readonly ctx: Record<string, unknown>;

  constructor(status: number, body: Partial<ErrorBody["error"]> = {}) {
    super(body.message ?? `HTTP ${status}`);
    this.status = status;
    this.code = body.code ?? (status === 0 ? "network_error" : "unknown_error");
    this.fields = body.fields ?? [];
    this.ctx = body.ctx ?? {};
  }
}

type Method = "GET" | "POST" | "PATCH" | "DELETE";

/**
 * JSON request to the API, with the response status (e.g. 201 created vs 200 already there).
 * Same origin: the session cookie goes along by itself. Every request with a body is
 * sent as application/json, which is also what the backend's CSRF guard expects.
 */
export async function request<T>(
  method: Method,
  path: string,
  body?: unknown,
): Promise<{ status: number; data: T }> {
  let res: Response;
  try {
    res = await fetch(path, {
      method,
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, { message: "Network error" });
  }
  if (res.status === 204) return { status: 204, data: undefined as T };
  const data: unknown = await res.json().catch(() => null);
  if (!res.ok) {
    const error = (data as ErrorBody | null)?.error;
    throw new ApiError(res.status, error ?? undefined);
  }
  return { status: res.status, data: data as T };
}

export async function api<T>(method: Method, path: string, body?: unknown): Promise<T> {
  return (await request<T>(method, path, body)).data;
}

export const get = <T>(path: string) => api<T>("GET", path);

/** Query string from defined values only. */
export function withQuery(path: string, params: Record<string, string | undefined>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== "") q.set(k, v);
  const s = q.toString();
  return s ? `${path}?${s}` : path;
}
