import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { WalkOption } from "../api/client";
import { OptionCard } from "./OptionCard";

const option: WalkOption = {
  station_id: "940GZZLUOXC",
  station_name: "Oxford Circus Underground Station",
  line_id: "victoria",
  line_name: "Victoria",
  direction: "inbound",
  destination_name: "Brixton Underground Station",
  platform_name: "Southbound - Platform 5",
  departure_time: "2026-11-23T08:11:37Z",
  walk_seconds: 57,
  wait_seconds: 130,
  margin_seconds: 85,
};

describe("OptionCard", () => {
  it("shows the station, line, destination, times and badge", () => {
    render(<OptionCard option={option} />);
    expect(screen.getByRole("heading", { name: "Oxford Circus" })).toBeInTheDocument();
    expect(screen.getByText("to Brixton")).toBeInTheDocument();
    expect(screen.getByText("Southbound - Platform 5")).toBeInTheDocument();
    expect(screen.getByText("08:11")).toBeInTheDocument();
    expect(screen.getByText("1 min walk")).toBeInTheDocument();
    expect(screen.getByText("2 min wait")).toBeInTheDocument();
    expect(screen.getByText("tight")).toBeInTheDocument();
  });

  it("colours the line in its official colour", () => {
    render(<OptionCard option={option} />);
    expect(screen.getByText("Victoria")).toHaveStyle({ backgroundColor: "#0098D4" });
  });

  it("shows departure time in London time in summer", () => {
    render(<OptionCard option={{ ...option, departure_time: "2026-07-01T08:11:00Z" }} />);
    expect(screen.getByText("09:11")).toBeInTheDocument();
  });

  it("falls back to the direction when there is no destination", () => {
    render(<OptionCard option={{ ...option, destination_name: null, margin_seconds: 400 }} />);
    expect(screen.getByText("to inbound")).toBeInTheDocument();
    expect(screen.getByText("comfortable")).toBeInTheDocument();
  });
});
