import { useEffect, useState } from "react";
import { fetchJourneys, type JourneysQuery, type JourneysResponse } from "../api/client";

export const REFRESH_MS = 30_000;

export interface JourneysState {
  data: JourneysResponse | null;
  error: string | null;
  loading: boolean;
  updatedAt: number | null;
}

const EMPTY: JourneysState = { data: null, error: null, loading: false, updatedAt: null };

/**
 * Journeys for `query`, refreshed every 30 s while the page is open, and straight away when
 * the page comes back into view (phones pause timers in background tabs).
 */
export function useJourneys(query: JourneysQuery | null): JourneysState {
  const [state, setState] = useState<JourneysState>(EMPTY);
  const key = query ? JSON.stringify(query) : null;

  useEffect(() => {
    if (!query) {
      setState(EMPTY);
      return;
    }
    let controller: AbortController | null = null;

    const load = async () => {
      controller?.abort();
      const current = new AbortController();
      controller = current;
      setState((s) => ({ ...s, loading: true }));
      try {
        const data = await fetchJourneys(query, current.signal);
        setState({ data, error: null, loading: false, updatedAt: Date.now() });
      } catch (err) {
        if (current.signal.aborted) return;
        const error = err instanceof Error ? err.message : "Something went wrong";
        setState((s) => ({ ...s, error, loading: false }));
      }
    };

    setState(EMPTY);
    void load();
    const id = setInterval(() => void load(), REFRESH_MS);
    const onVisible = () => {
      if (document.visibilityState === "visible") void load();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      clearInterval(id);
      document.removeEventListener("visibilitychange", onVisible);
      controller?.abort();
    };
    // `key` captures every field of `query`; the object itself is new on each render.
  }, [key]);

  return state;
}
