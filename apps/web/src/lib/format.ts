/** Dropped from names to keep cards short. Other suffixes (" DLR Station") tell stations apart. */
const TUBE_SUFFIX = " Underground Station";

/** "Bank Underground Station" -> "Bank". */
export function shortName(name: string): string {
  return name.endsWith(TUBE_SUFFIX) ? name.slice(0, -TUBE_SUFFIX.length) : name;
}

/** Walking time, rounded up so it never looks shorter than it is. */
export function walkText(seconds: number): string {
  return `${Math.ceil(seconds / 60)} min walk`;
}

/** Time on the platform, rounded down so it never looks longer than it is. */
export function waitText(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  return minutes < 1 ? "under 1 min wait" : `${minutes} min wait`;
}

/** "22:11" in London time, whatever the phone's time zone. */
export function clockTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/London",
  });
}

export function agoText(ms: number): string {
  const seconds = Math.max(0, Math.round(ms / 1000));
  return seconds < 60 ? `${seconds}s ago` : `${Math.floor(seconds / 60)}m ago`;
}
