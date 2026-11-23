import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import type { JourneysResponse } from "./api/client";

const ambiguous: JourneysResponse = {
  kind: "ambiguous",
  from_options: [],
  to_options: [
    { value: "1000173", name: "Oxford Circus", place_type: "StopPoint" },
    { value: "1000174", name: "Oxford Street", place_type: "Address" },
  ],
};

const found: JourneysResponse = {
  kind: "journeys",
  journeys: [
    {
      leave_by: "2026-11-23T08:03:00Z",
      arrival_time: "2026-11-23T08:20:00Z",
      margin_seconds: 400,
      legs: [{ kind: "walk", from_name: "a", to_name: "Oxford Circus", distance_m: 900, street_seconds: 600, station_seconds: 0, seconds: 600 }],
    },
  ],
};

/** A fake API: no place suggestions; /journeys answers come from `journeys` in turn. */
function fakeApi(...journeys: JourneysResponse[]) {
  return vi.fn(async (url: string) => {
    if (new URL(url).pathname === "/places") return new Response("[]");
    const next = journeys.length > 1 ? journeys.shift()! : journeys[0]!;
    return new Response(JSON.stringify(next));
  });
}

const journeyCalls = (mock: ReturnType<typeof fakeApi>) =>
  mock.mock.calls.map(([url]) => new URL(String(url))).filter((u) => u.pathname === "/journeys");

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("App", () => {
  it("asks which place was meant, then shows routes to it", async () => {
    const fetchMock = fakeApi(ambiguous, found);
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    await userEvent.type(screen.getByLabelText("From"), "Baker Street");
    await userEvent.type(screen.getByLabelText("Where to?"), "oxford");
    await userEvent.click(screen.getByRole("button", { name: "Go" }));

    await userEvent.click(await screen.findByRole("button", { name: "Oxford Circus" }));
    expect(await screen.findByRole("heading", { name: "Arrive 08:20" })).toBeInTheDocument();

    const [first, second] = journeyCalls(fetchMock).map((u) => u.searchParams);
    expect(first?.get("from")).toBe("Baker Street");
    expect(first?.get("to")).toBe("oxford");
    expect(second?.get("to")).toBe("1000173");
    expect(second?.get("speed_kmh")).toBe("5.5");
    expect(second?.get("risk")).toBe("medium");
  });

  it("uses the phone's location as the start", async () => {
    const fetchMock = fakeApi(found);
    vi.stubGlobal("fetch", fetchMock);
    const getCurrentPosition = vi.fn((ok: PositionCallback) =>
      ok({ coords: { latitude: 51.5226, longitude: -0.1571 } } as GeolocationPosition),
    );
    vi.stubGlobal("navigator", { ...navigator, geolocation: { getCurrentPosition } });
    render(<App />);

    await userEvent.click(screen.getByRole("button", { name: "Use my location" }));
    await userEvent.type(screen.getByLabelText("Where to?"), "Bank");
    await userEvent.click(screen.getByRole("button", { name: "Go" }));

    expect(await screen.findByText("Your location → Bank")).toBeInTheDocument();
    expect(journeyCalls(fetchMock)[0]?.searchParams.get("from")).toBe("51.5226,-0.1571");
  });
});
