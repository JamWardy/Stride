export type Badge = "comfortable" | "tight" | "risky";

/**
 * How relaxed the walk is, from the slack left after the risk setting's safety margin.
 * Every option the API returns is catchable; this only says how much room there is.
 */
export const TIGHT_BELOW_S = 180;
export const RISKY_BELOW_S = 60;

export function marginBadge(marginSeconds: number): Badge {
  if (marginSeconds < RISKY_BELOW_S) return "risky";
  if (marginSeconds < TIGHT_BELOW_S) return "tight";
  return "comfortable";
}
