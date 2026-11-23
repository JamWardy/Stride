import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { JourneyOption, TrainLeg } from "../api/client";
import { JourneyCard } from "./JourneyCard";

const NOW = Date.parse("2026-11-23T08:00:00Z");

const victoria: TrainLeg = {
  kind: "train",
  line_id: "victoria",
  line_name: "Victoria",
  from_stop_id: "940GZZLUOXC",
  from_name: "Oxford Circus Underground Station",
  to_stop_id: "940GZZLUVIC",
  to_name: "Victoria Underground Station",
  destination_name: "Brixton Underground Station",
  platform_name: "Southbound - Platform 5",
  departure_time: "2026-11-23T08:06:00Z",
  arrival_time: "2026-11-23T08:11:00Z",
  wait_seconds: 130,
  margin_seconds: 85,
  source: "live",
};

const journey: JourneyOption = {
  leave_by: "2026-11-23T08:03:30Z",
  arrival_time: "2026-11-23T08:20:00Z",
  margin_seconds: 85,
  legs: [
    { kind: "walk", from_name: "1 Regent St", to_name: "Oxford Circus Underground Station", distance_m: 300, street_seconds: 200, station_seconds: 70, seconds: 270 },
    victoria,
    { kind: "change", stop_id: "940GZZLUVIC", name: "Victoria Underground Station", seconds: 150 },
    { ...victoria, line_id: "district", line_name: "District", source: "timetable", platform_name: null },
    { kind: "walk", from_name: "Victoria", to_name: "10 Buckingham Gate", distance_m: 400, street_seconds: 240, station_seconds: 60, seconds: 300 },
  ],
};

describe("JourneyCard", () => {
  it("shows when to leave, when you arrive and how tight it is", () => {
    render(<JourneyCard journey={journey} now={NOW} />);
    expect(screen.getByText(/Leave in 3 min/)).toHaveTextContent("Leave in 3 min · by 08:03");
    expect(screen.getByRole("heading", { name: "Arrive 08:20" })).toBeInTheDocument();
    expect(screen.getByText("tight")).toBeInTheDocument();
  });

  it("lists each leg in order", () => {
    render(<JourneyCard journey={journey} now={NOW} />);
    const legs = within(screen.getByRole("list")).getAllByRole("listitem").map((li) => li.textContent);
    expect(legs[0]).toBe("Walk 5 min to Oxford Circus");
    expect(legs[1]).toContain("08:06from Oxford Circus");
    expect(legs[1]).toContain("towards Brixton · Southbound - Platform 5 · 2 min wait");
    expect(legs[1]).toContain("Get off at Victoria, 08:11");
    expect(legs[2]).toBe("Change at Victoria, 3 min");
    expect(legs[4]).toBe("Walk 5 min to 10 Buckingham Gate");
  });

  it("colours lines and marks trains taken from the timetable", () => {
    render(<JourneyCard journey={journey} now={NOW} />);
    expect(screen.getByText("Victoria")).toHaveStyle({ backgroundColor: "#0098D4" });
    expect(screen.getAllByText("timetable")).toHaveLength(1);
  });

  it("has no badge for a walk with no trains, and says leave now", () => {
    const walkOnly: JourneyOption = { ...journey, leave_by: "2026-11-23T08:00:00Z", margin_seconds: null, legs: [journey.legs[0]!] };
    render(<JourneyCard journey={walkOnly} now={NOW} />);
    expect(screen.getByText("Leave now")).toBeInTheDocument();
    expect(screen.queryByText(/comfortable|tight|risky/)).not.toBeInTheDocument();
  });
});
