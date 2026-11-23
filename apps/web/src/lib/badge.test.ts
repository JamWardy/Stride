import { describe, expect, it } from "vitest";
import { marginBadge } from "./badge";

describe("marginBadge", () => {
  it.each([
    [0, "risky"],
    [59.9, "risky"],
    [60, "tight"],
    [179.9, "tight"],
    [180, "comfortable"],
    [900, "comfortable"],
  ])("%s s of slack is %s", (margin, badge) => {
    expect(marginBadge(margin)).toBe(badge);
  });
});
