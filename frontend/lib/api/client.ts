/**
 * A small typed fetch wrapper over the generated OpenAPI schema.
 *
 * 20 endpoints doesn't justify a full client generator with its own runtime
 * (openapi-fetch, etc.) -- this file is the whole client. `schema.d.ts` is
 * checked into git so the app builds without a running backend; regenerate
 * it with `make gen-api` whenever the API shape changes.
 *
 * Client-side only (uses `window.location` to build relative URLs through
 * the Next.js dev proxy) -- every page that calls this is a client
 * component, matching the plan's read-only-SPA-over-one-project design.
 */
import type { paths } from "./schema";

export class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(status: number, body: unknown) {
    const detail =
      typeof body === "object" && body !== null && "detail" in body
        ? String((body as { detail: unknown }).detail)
        : `Request failed with status ${status}`;
    super(detail);
    this.status = status;
    this.body = body;
  }
}

type Method = "get" | "post" | "patch" | "delete";

type PathsWithMethod<M extends Method> = {
  [P in keyof paths]: paths[P] extends { [K in M]: unknown } ? P : never;
}[keyof paths];

type RequestBody<P extends keyof paths, M extends Method> = paths[P] extends {
  [K in M]: { requestBody: { content: { "application/json": infer B } } };
}
  ? B
  : undefined;

type ResponseBody<P extends keyof paths, M extends Method> = paths[P] extends {
  [K in M]: {
    responses: { 200: { content: { "application/json": infer R } } };
  };
}
  ? R
  : paths[P] extends {
        [K in M]: {
          responses: { 201: { content: { "application/json": infer R } } };
        };
      }
    ? R
    : paths[P] extends {
          [K in M]: {
            responses: { 202: { content: { "application/json": infer R } } };
          };
        }
      ? R
      : unknown;

/** Fills `{param}` placeholders in a path template from a plain object. */
function interpolate(path: string, params?: Record<string, string | number>): string {
  if (!params) return path;
  return path.replace(/\{([^}]+)\}/g, (_match, key: string) => {
    const value = params[key];
    if (value === undefined) {
      throw new Error(`Missing path parameter "${key}" for ${path}`);
    }
    return encodeURIComponent(String(value));
  });
}

async function request<P extends keyof paths, M extends Method>(
  method: M,
  path: P,
  options?: {
    params?: Record<string, string | number>;
    query?: Record<string, string | number | boolean | undefined>;
    body?: RequestBody<P, M>;
  },
): Promise<ResponseBody<P, M>> {
  const url = new URL(interpolate(path as string, options?.params), window.location.origin);
  if (options?.query) {
    for (const [key, value] of Object.entries(options.query)) {
      if (value !== undefined) url.searchParams.set(key, String(value));
    }
  }

  const response = await fetch(url.toString(), {
    method: method.toUpperCase(),
    headers: options?.body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: options?.body !== undefined ? JSON.stringify(options.body) : undefined,
  });

  if (!response.ok) {
    let body: unknown;
    try {
      body = await response.json();
    } catch {
      body = await response.text();
    }
    throw new ApiError(response.status, body);
  }

  if (response.status === 204) {
    return undefined as ResponseBody<P, M>;
  }
  return (await response.json()) as ResponseBody<P, M>;
}

export const api = {
  get: <P extends PathsWithMethod<"get">>(
    path: P,
    options?: {
      params?: Record<string, string | number>;
      query?: Record<string, string | number | boolean | undefined>;
    },
  ) => request("get", path, options),

  post: <P extends PathsWithMethod<"post">>(
    path: P,
    options?: {
      params?: Record<string, string | number>;
      body?: RequestBody<P, "post">;
    },
  ) => request("post", path, options),

  patch: <P extends PathsWithMethod<"patch">>(
    path: P,
    options?: { params?: Record<string, string | number>; body?: RequestBody<P, "patch"> },
  ) => request("patch", path, options),

  delete: <P extends PathsWithMethod<"delete">>(
    path: P,
    options?: { params?: Record<string, string | number> },
  ) => request("delete", path, options),
};

/** For multipart/form-data endpoints (draft upload, reference import),
 * which don't fit the JSON-body shape above. */
export async function postFormData(path: string, file: File, params?: Record<string, string>) {
  const url = new URL(interpolate(path, params), window.location.origin);
  const form = new FormData();
  form.append("file", file);

  const response = await fetch(url.toString(), { method: "POST", body: form });
  if (!response.ok) {
    let body: unknown;
    try {
      body = await response.json();
    } catch {
      body = await response.text();
    }
    throw new ApiError(response.status, body);
  }
  return response.json();
}

export function downloadUrl(exportId: string): string {
  return `/api/v1/exports/${exportId}/download`;
}

export function missingAbstractsTemplateUrl(year: number | null): string {
  return year === null
    ? "/api/v1/library/missing-abstracts-template"
    : `/api/v1/library/missing-abstracts-template?year=${year}`;
}
