import { describe, expect, it } from "vitest";
import { clockTime, minutesDown, minutesUp, shortName, untilText } from "./format";

describe("format", () => {
  it("shortens station names but keeps DLR apart", () => {
    expect(shortName("Bank Underground Station")).toBe("Bank");
    expect(shortName("Shenfield Rail Station")).toBe("Shenfield");
    expect(shortName("Bank DLR Station")).toBe("Bank DLR Station");
  });

  it("rounds walks up and waits down", () => {
    expect([minutesUp(61), minutesUp(60), minutesDown(119), minutesDown(-5)]).toEqual([2, 1, 1, 0]);
  });

  it("shows London time in summer and winter", () => {
    expect(clockTime("2026-07-01T08:11:00Z")).toBe("09:11");
    expect(clockTime("2026-11-23T08:11:00Z")).toBe("08:11");
  });

  it("says now under a minute", () => {
    const now = Date.parse("2026-11-23T08:00:00Z");
    expect(untilText("2026-11-23T08:00:50Z", now)).toBe("now");
    expect(untilText("2026-11-23T08:03:10Z", now)).toBe("in 3 min");
  });
});
