/** Suffixes dropped to keep cards short. " DLR Station" is kept: it tells Bank DLR from Bank. */
const SUFFIXES = [" Underground Station", " Rail Station"];

/** "Bank Underground Station" -> "Bank". */
export function shortName(name: string): string {
  const suffix = SUFFIXES.find((s) => name.endsWith(s));
  return suffix ? name.slice(0, -suffix.length) : name;
}

/** Whole minutes, rounded up so a walk never looks shorter than it is. */
export function minutesUp(seconds: number): number {
  return Math.ceil(seconds / 60);
}

/** Whole minutes, rounded down so a wait never looks longer than it is. */
export function minutesDown(seconds: number): number {
  return Math.max(0, Math.floor(seconds / 60));
}

/** "22:11" in London time, whatever the phone's time zone. */
export function clockTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/London",
  });
}

/** "now", "in 1 min", "in 12 min" until `iso`. */
export function untilText(iso: string, now: number): string {
  const minutes = Math.floor((new Date(iso).getTime() - now) / 60_000);
  return minutes < 1 ? "now" : `in ${minutes} min`;
}

export function agoText(ms: number): string {
  const seconds = Math.max(0, Math.round(ms / 1000));
  return seconds < 60 ? `${seconds}s ago` : `${Math.floor(seconds / 60)}m ago`;
}
