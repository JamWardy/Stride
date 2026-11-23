import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { StationSearch } from "./StationSearch";

const oxford = { id: "940GZZLUOXC", name: "Oxford Circus Underground Station", lat: 51.515, lon: -0.142 };

afterEach(() => vi.unstubAllGlobals());

describe("StationSearch", () => {
  it("searches as you type and hands back the chosen station", async () => {
    const fetchMock = vi.fn(async (_url: string) => new Response(JSON.stringify([oxford])));
    vi.stubGlobal("fetch", fetchMock);
    const onSelect = vi.fn();
    render(<StationSearch onSelect={onSelect} />);

    await userEvent.type(screen.getByLabelText("Or start from a station"), "oxford");
    await userEvent.click(await screen.findByRole("button", { name: "Oxford Circus" }));

    expect(onSelect).toHaveBeenCalledWith(oxford);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain("/stations/search?q=oxford");
    expect(screen.queryByRole("button", { name: "Oxford Circus" })).not.toBeInTheDocument();
  });

  it("shows the API's error message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ detail: "TfL request failed: [503] Down" }), { status: 502 })),
    );
    render(<StationSearch onSelect={() => {}} />);
    await userEvent.type(screen.getByLabelText("Or start from a station"), "bank");
    expect(await screen.findByText("TfL request failed: [503] Down")).toBeInTheDocument();
  });
});
