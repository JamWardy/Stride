import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { REFRESH_MS, useOptions } from "./useOptions";

const query = { lat: 51.515, lon: -0.141, speed_kmh: 5.5, risk: "medium" as const };

beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal("fetch", vi.fn(async (_url: string) => new Response("[]")));
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("useOptions", () => {
  it("loads straight away, then refreshes every 30 s", async () => {
    const { result } = renderHook(() => useOptions(query));
    await act(() => vi.advanceTimersByTimeAsync(0));
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(result.current.options).toEqual([]);
    const firstUpdate = result.current.updatedAt;

    await act(() => vi.advanceTimersByTimeAsync(REFRESH_MS));
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(result.current.updatedAt).toBeGreaterThan(firstUpdate!);
  });

  it("sends the walking settings to the API", async () => {
    renderHook(() => useOptions(query));
    await act(() => vi.advanceTimersByTimeAsync(0));
    const url = String(vi.mocked(fetch).mock.calls[0]?.[0]);
    expect(url).toContain("/options?lat=51.515&lon=-0.141&speed_kmh=5.5&risk=medium");
  });

  it("stops refreshing once unmounted", async () => {
    const { unmount } = renderHook(() => useOptions(query));
    await act(() => vi.advanceTimersByTimeAsync(0));
    unmount();
    await vi.advanceTimersByTimeAsync(REFRESH_MS * 3);
    expect(fetch).toHaveBeenCalledTimes(1);
  });
});
