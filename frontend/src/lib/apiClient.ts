import { API_BASE } from "@/src/config/constants";

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

/** The single fetch entry point: fills in API_BASE and throws ApiError on a non-2xx response. */
export async function apiFetch(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const url = path.startsWith("http") ? path : `${API_BASE}${path}`;
  const headers = new Headers(init.headers);

  const res = await fetch(url, { ...init, headers });

  if (!res.ok) {
    let detail = res.statusText || `HTTP ${res.status}`;
    try {
      const body = await res.clone().json();
      if (body?.detail) detail = String(body.detail);
    } catch {
      // Response isn't JSON; keep the status text.
    }
    throw new ApiError(res.status, detail);
  }

  return res;
}

/** Convenience wrapper: fetches JSON directly. */
export async function apiJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await apiFetch(path, init);
  return (await res.json()) as T;
}
