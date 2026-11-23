import type { ChangeLeg, JourneyLeg, JourneyOption, TrainLeg, WalkLeg } from "../api/client";
import { marginBadge } from "../lib/badge";
import { clockTime, minutesDown, minutesUp, shortName, untilText } from "../lib/format";
import { lineColours } from "../lib/lines";

function Walk({ leg }: { leg: WalkLeg }) {
  if (leg.distance_m === 0) {
    return <li className="leg leg-walk">Into {shortName(leg.to_name)}, {minutesUp(leg.seconds)} min</li>;
  }
  return (
    <li className="leg leg-walk">
      Walk {minutesUp(leg.seconds)} min to {shortName(leg.to_name)}
    </li>
  );
}

function Change({ leg }: { leg: ChangeLeg }) {
  return (
    <li className="leg leg-change">
      Change at {shortName(leg.name)}, {minutesUp(leg.seconds)} min
    </li>
  );
}

function Train({ leg }: { leg: TrainLeg }) {
  const wait = minutesDown(leg.wait_seconds);
  return (
    <li className="leg leg-train">
      <div className="train-top">
        <span className="line" style={lineColours(leg.line_id)}>
          {leg.line_name}
        </span>
        <strong>{clockTime(leg.departure_time)}</strong>
        <span>from {shortName(leg.from_name)}</span>
        {leg.source === "timetable" && <span className="scheduled">timetable</span>}
      </div>
      <div className="train-detail">
        {leg.destination_name && <>towards {shortName(leg.destination_name)} · </>}
        {leg.platform_name && <>{leg.platform_name} · </>}
        {wait < 1 ? "under 1 min wait" : `${wait} min wait`}
      </div>
      <div className="train-detail">
        Get off at {shortName(leg.to_name)}, {clockTime(leg.arrival_time)}
      </div>
    </li>
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
        {badge && <span className={`badge badge-${badge}`}>{badge}</span>}
      </div>
      <ol className="legs">
        {journey.legs.map((leg, i) => (
          <Leg key={i} leg={leg} />
        ))}
      </ol>
    </li>
  );
}
