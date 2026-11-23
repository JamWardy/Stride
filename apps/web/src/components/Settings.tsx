import type { CSSProperties } from "react";
import type { Risk } from "../api/client";

export const RISKS: Risk[] = ["low", "medium", "high"];
const MIN_KMH = 3;
const MAX_KMH = 8;

interface Props {
  speed: number;
  onSpeed: (kmh: number) => void;
  risk: Risk;
  onRisk: (risk: Risk) => void;
}

export function Settings({ speed, onSpeed, risk, onRisk }: Props) {
  const fill = `${((speed - MIN_KMH) / (MAX_KMH - MIN_KMH)) * 100}%`;
  return (
    <div className="settings">
      <label className="speed">
        <span className="speed-head">
          <span className="field-label">Walking speed</span>
          <span className="speed-value">{speed.toFixed(1)} km/h</span>
        </span>
        <input
          type="range"
          min={MIN_KMH}
          max={MAX_KMH}
          step={0.5}
          value={speed}
          style={{ "--fill": fill } as CSSProperties}
          onChange={(e) => onSpeed(Number(e.target.value))}
        />
      </label>
      <div className="risk" role="radiogroup" aria-label="Risk">
        <span className="field-label risk-label">Risk</span>
        {RISKS.map((r) => (
          <button
            key={r}
            type="button"
            role="radio"
            aria-checked={risk === r}
            className={risk === r ? "selected" : ""}
            onClick={() => onRisk(r)}
          >
            {r}
          </button>
        ))}
      </div>
    </div>
  );
}
