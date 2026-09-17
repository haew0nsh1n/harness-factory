type ApiEnvelope<T> =
  | ({ ok: true } & T)
  | {
      ok: false;
      code?: string;
      error?: string;
    };

export interface ApiErrorPayload {
  ok?: false;
  code?: string;
  error?: string;
  finding?: unknown;
  design?: unknown;
  detail?: unknown;
}

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly payload: ApiErrorPayload | null;

  constructor(
    code: string,
    message: string,
    status: number,
    payload: ApiErrorPayload | null = null,
  ) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.payload = payload;
  }
}

export interface ApiOptions {
  method?: "GET" | "POST" | "PUT" | "DELETE";
  body?: unknown;
}

async function request(path: string, options: ApiOptions = {}): Promise<Response> {
  const normalizedPath = normalizePath(path);
  const headers = new Headers({ accept: "application/json" });
  let body: string | undefined;

  if (options.body !== undefined) {
    headers.set("content-type", "application/json");
    body = JSON.stringify(options.body);
  }

  return fetch(`/api/control-plane${normalizedPath}`, {
    method: options.method ?? "GET",
    credentials: "same-origin",
    headers,
    body,
  });
}

function normalizePath(path: string): string {
  if (!path.startsWith("/")) {
    return `/${path}`;
  }
  return path;
}

function unwrapOkEnvelope<T>(payload: ApiEnvelope<T>): T {
  if (!payload.ok) {
    throw new ApiError(
      payload.code ?? "request_failed",
      payload.error ?? "Request failed",
      500,
      payload,
    );
  }

  const entries = Object.entries(payload).filter(([key]) => key !== "ok");
  if (entries.length === 1) {
    return entries[0]?.[1] as T;
  }

  return payload as T;
}

export async function api<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const response = await request(path, options);
  const payload = (await response.json()) as ApiEnvelope<T>;
  if (!response.ok || payload.ok === false) {
    const errorPayload = payload.ok === false ? payload : null;
    throw new ApiError(
      errorPayload?.code ?? "request_failed",
      errorPayload?.error ?? "Request failed",
      response.status,
      errorPayload,
    );
  }

  return unwrapOkEnvelope(payload);
}

export async function apiRaw<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const response = await request(path, options);
  const payload = (await response.json()) as T | { code?: string; error?: string };

  if (!response.ok) {
    const errorPayload =
      payload && typeof payload === "object" && "error" in payload ? payload : null;
    throw new ApiError(
      errorPayload?.code ?? "request_failed",
      errorPayload?.error ?? "Request failed",
      response.status,
      errorPayload,
    );
  }

  return payload as T;
}
