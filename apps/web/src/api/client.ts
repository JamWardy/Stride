import type { components, paths } from "./schema";

type Schemas = components["schemas"];
export type JourneyOption = Schemas["JourneyOption"];
export type JourneyLeg = JourneyOption["legs"][number];
export type WalkLeg = Schemas["WalkLeg"];
export type ChangeLeg = Schemas["ChangeLeg"];
export type TrainLeg = Schemas["TrainLeg"];
export type PlaceChoice = Schemas["PlaceChoice"];
export type JourneysResponse = Schemas["JourneysFound"] | Schemas["AmbiguousPlaces"];
export type Suggestion = Schemas["StationSuggestion"] | Schemas["PlaceSuggestion"];
export type JourneysQuery = paths["/journeys"]["get"]["parameters"]["query"];
export type Risk = NonNullable<JourneysQuery["risk"]>;

/** Where the API runs. The TfL key stays there; the browser never sees it. */
export const API_URL: string = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function getJson<T>(path: string, params: Record<string, string | number | undefined>, signal?: AbortSignal): Promise<T> {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) query.set(key, String(value));
  }
  const response = await fetch(`${API_URL}${path}?${query}`, { signal });
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    const detail = body && typeof body === "object" && "detail" in body ? body.detail : null;
    throw new Error(typeof detail === "string" ? detail : `Request failed (${response.status})`);
  }
  return (await response.json()) as T;
}

export function fetchJourneys(query: JourneysQuery, signal?: AbortSignal): Promise<JourneysResponse> {
  return getJson("/journeys", query, signal);
}

/** Stations first, then Google's places. `session` groups one search's keystrokes for billing. */
export function suggestPlaces(q: string, session: string, signal?: AbortSignal): Promise<Suggestion[]> {
  return getJson("/places", { q, session }, signal);
}

/** A Google place's "lat,lon"; ends the search session. */
export async function resolvePlace(placeId: string, session: string): Promise<string> {
  const { value } = await getJson<{ value: string }>(`/places/${encodeURIComponent(placeId)}`, { session });
  return value;
}

/** A random token for one search. Works without HTTPS, unlike crypto.randomUUID. */
export function newSessionToken(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}
