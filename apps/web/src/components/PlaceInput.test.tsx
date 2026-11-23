import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Suggestion } from "../api/client";
import { type Place, PlaceInput } from "./PlaceInput";

const suggestions: Suggestion[] = [
  { kind: "station", name: "King's Cross & St Pancras International", value: "1000129" },
  { kind: "place", name: "BAO King's Cross", detail: "Lewis Cubitt Square, London", place_id: "ChIJabc" },
];

function fakeApi() {
  return vi.fn(async (url: string) => {
    const u = new URL(url);
    if (u.pathname === "/places") return new Response(JSON.stringify(suggestions));
    return new Response(JSON.stringify({ value: "51.5355,-0.1256" })); // /places/ChIJabc
  });
}

function Harness({ onSelect }: { onSelect: (p: Place) => void }) {
  const [text, setText] = useState("");
  return <PlaceInput id="to" label="Where to?" placeholder="" text={text} onText={setText} onSelect={onSelect} />;
}

afterEach(() => vi.unstubAllGlobals());

describe("PlaceInput", () => {
  it("lists stations first, then Google's places", async () => {
    vi.stubGlobal("fetch", fakeApi());
    render(<Harness onSelect={() => {}} />);
    await userEvent.type(screen.getByLabelText("Where to?"), "kings");
    const options = await screen.findAllByRole("button");
    expect(options.map((b) => b.textContent)).toEqual([
      "King's Cross & St Pancras InternationalStation",
      "BAO King's CrossLewis Cubitt Square, London",
    ]);
  });

  it("uses a station's value directly", async () => {
    const api = fakeApi();
    vi.stubGlobal("fetch", api);
    const onSelect = vi.fn();
    render(<Harness onSelect={onSelect} />);
    await userEvent.type(screen.getByLabelText("Where to?"), "kings");
    await userEvent.click(await screen.findByRole("button", { name: /St Pancras/ }));
    expect(onSelect).toHaveBeenCalledWith({ label: "King's Cross & St Pancras International", value: "1000129" });
    expect(api.mock.calls.every(([url]) => new URL(url).pathname === "/places")).toBe(true);
  });

  it("resolves a Google place in the same session, then starts a new one", async () => {
    const api = fakeApi();
    vi.stubGlobal("fetch", api);
    const onSelect = vi.fn();
    render(<Harness onSelect={onSelect} />);
    const input = screen.getByLabelText("Where to?");

    await userEvent.type(input, "bao");
    await userEvent.click(await screen.findByRole("button", { name: /BAO/ }));
    expect(onSelect).toHaveBeenCalledWith({ label: "BAO King's Cross", value: "51.5355,-0.1256" });
    expect(input).toHaveValue("");

    await userEvent.type(input, "bank");
    await screen.findAllByRole("button");
    const urls = api.mock.calls.map(([url]) => new URL(url));
    const firstSearch = urls.find((u) => u.searchParams.get("q") === "bao")!;
    const resolve = urls.find((u) => u.pathname === "/places/ChIJabc")!;
    const secondSearch = urls.find((u) => u.searchParams.get("q") === "bank")!;
    expect(resolve.searchParams.get("session")).toBe(firstSearch.searchParams.get("session"));
    expect(secondSearch.searchParams.get("session")).not.toBe(firstSearch.searchParams.get("session"));
  });
});
