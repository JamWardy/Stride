import type { components, paths } from "./schema";

export type WalkOption = components["schemas"]["WalkOption"];
export type Station = components["schemas"]["Station"];
export type OptionsQuery = paths["/options"]["get"]["parameters"]["query"];
export type Risk = NonNullable<OptionsQuery["risk"]>;

/** Where the API runs. The TfL key stays there; the browser never sees it. */
export const API_URL: string = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function getJson<T>(path: string, params: Record<string, string | number>, signal?: AbortSignal): Promise<T> {
  const query = new URLSearchParams(Object.entries(params).map(([k, v]) => [k, String(v)]));
  const response = await fetch(`${API_URL}${path}?${query}`, { signal });
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    const detail = body && typeof body === "object" && "detail" in body ? body.detail : null;
    throw new Error(typeof detail === "string" ? detail : `Request failed (${response.status})`);
  }
  return (await response.json()) as T;
}

export function fetchOptions(query: OptionsQuery, signal?: AbortSignal): Promise<WalkOption[]> {
  const params = Object.fromEntries(Object.entries(query).filter(([, v]) => v !== undefined));
  return getJson("/options", params, signal);
}

export function searchStations(q: string, signal?: AbortSignal): Promise<Station[]> {
  return getJson("/stations/search", { q }, signal);
}
