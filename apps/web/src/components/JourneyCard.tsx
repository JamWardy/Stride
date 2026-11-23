import { ArrowLeftRight, Footprints, TrainFront } from "lucide-react";
import type { ReactNode } from "react";
import type { ChangeLeg, JourneyLeg, JourneyOption, TrainLeg, WalkLeg } from "../api/client";
import { marginBadge } from "../lib/badge";
import { clockTime, minutesDown, minutesUp, shortName, untilText } from "../lib/format";
import { lineColours } from "../lib/lines";

const ICON = { size: 18, strokeWidth: 2.5, "aria-hidden": true } as const;

function LegRow({ kind, tile, icon, children }: { kind: string; tile: string; icon: ReactNode; children: ReactNode }) {
  return (
    <li className={`leg leg-${kind}`}>
      <span className={`tile ${tile}`}>{icon}</span>
      <div className="leg-body">{children}</div>
    </li>
  );
}

function Walk({ leg }: { leg: WalkLeg }) {
  const text =
    leg.distance_m === 0
      ? `Into ${shortName(leg.to_name)}, ${minutesUp(leg.seconds)} min`
      : `Walk ${minutesUp(leg.seconds)} min to ${shortName(leg.to_name)}`;
  return (
    <LegRow kind="walk" tile="tile-mint" icon={<Footprints {...ICON} />}>
      {text}
    </LegRow>
  );
}

function Change({ leg }: { leg: ChangeLeg }) {
  return (
    <LegRow kind="change" tile="tile-lavender" icon={<ArrowLeftRight {...ICON} />}>
      Change at {shortName(leg.name)}, {minutesUp(leg.seconds)} min
    </LegRow>
  );
}

function Train({ leg }: { leg: TrainLeg }) {
  const wait = minutesDown(leg.wait_seconds);
  return (
    <LegRow kind="train" tile="tile-sky" icon={<TrainFront {...ICON} />}>
      <div className="train-top">
        <span className="line" style={lineColours(leg.line_id)}>
          {leg.line_name}
        </span>
        <span className="train-time">{clockTime(leg.departure_time)}</span>
        <span>from {shortName(leg.from_name)}</span>
        {leg.source === "timetable" && <span className="pill scheduled">timetable</span>}
      </div>
      <div className="train-detail">
        {leg.destination_name && <>towards {shortName(leg.destination_name)} · </>}
        {leg.platform_name && <>{leg.platform_name} · </>}
        {wait < 1 ? "under 1 min wait" : `${wait} min wait`}
      </div>
      <div className="train-detail">
        Get off at {shortName(leg.to_name)}, {clockTime(leg.arrival_time)}
      </div>
    </LegRow>
  );
}

function Leg({ leg }: { leg: JourneyLeg }) {
  switch (leg.kind) {
    case "walk":
      return <Walk leg={leg} />;
    case "change":
      return <Change leg={leg} />;
    case "train":
      return <Train leg={leg} />;
  }
}

export function JourneyCard({ journey, now }: { journey: JourneyOption; now: number }) {
  const badge = journey.margin_seconds === null ? null : marginBadge(journey.margin_seconds);
  return (
    <li className="card">
      <div className="card-top">
        <div>
          <div className="leave">
            Leave {untilText(journey.leave_by, now)}
            {untilText(journey.leave_by, now) !== "now" && <> · by {clockTime(journey.leave_by)}</>}
          </div>
          <h2 className="arrive">Arrive {clockTime(journey.arrival_time)}</h2>
        </div>
        {badge && <span className={`pill badge badge-${badge}`}>{badge}</span>}
      </div>
      <ol className="legs">
        {journey.legs.map((leg, i) => (
          <Leg key={i} leg={leg} />
        ))}
      </ol>
    </li>
  );
}
