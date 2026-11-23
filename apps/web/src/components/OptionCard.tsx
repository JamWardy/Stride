import type { WalkOption } from "../api/client";
import { marginBadge } from "../lib/badge";
import { clockTime, shortName, waitText, walkText } from "../lib/format";
import { lineColours } from "../lib/lines";

export function OptionCard({ option }: { option: WalkOption }) {
  const badge = marginBadge(option.margin_seconds);
  const towards = option.destination_name ?? option.direction;
  return (
    <li className="card">
      <div className="card-top">
        <h2 className="station">{shortName(option.station_name)}</h2>
        <span className={`badge badge-${badge}`}>{badge}</span>
      </div>
      <div className="line-row">
        <span className="line" style={lineColours(option.line_id)}>
          {option.line_name}
        </span>
        {towards && <span className="towards">to {shortName(towards)}</span>}
      </div>
      {option.platform_name && <div className="platform">{option.platform_name}</div>}
      <dl className="facts">
        <div>
          <dt>Departs</dt>
          <dd>{clockTime(option.departure_time)}</dd>
        </div>
        <div>
          <dt>Walk</dt>
          <dd>{walkText(option.walk_seconds)}</dd>
        </div>
        <div>
          <dt>Platform</dt>
          <dd>{waitText(option.wait_seconds)}</dd>
        </div>
      </dl>
    </li>
  );
}
