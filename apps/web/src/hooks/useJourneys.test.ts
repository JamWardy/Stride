import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { REFRESH_MS, useJourneys } from "./useJourneys";

const query = { from: "51.5,-0.14", to: "Bank", speed_kmh: 5.5, risk: "medium" as const };
const body = JSON.stringify({ kind: "journeys", journeys: [] });

beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal("fetch", vi.fn(async (_url: string) => new Response(body)));
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("useJourneys", () => {
  it("loads straight away, then refreshes every 30 s", async () => {
    const { result } = renderHook(() => useJourneys(query));
    await act(() => vi.advanceTimersByTimeAsync(0));
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(result.current.data).toEqual({ kind: "journeys", journeys: [] });
    const firstUpdate = result.current.updatedAt;

    await act(() => vi.advanceTimersByTimeAsync(REFRESH_MS));
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(result.current.updatedAt).toBeGreaterThan(firstUpdate!);
  });

  it("stops refreshing once unmounted", async () => {
    const { unmount } = renderHook(() => useJourneys(query));
    await act(() => vi.advanceTimersByTimeAsync(0));
    unmount();
    await vi.advanceTimersByTimeAsync(REFRESH_MS * 3);
    expect(fetch).toHaveBeenCalledTimes(1);
  });
});
