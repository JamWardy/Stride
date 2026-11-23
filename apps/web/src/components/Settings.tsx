import type { Risk } from "../api/client";

export const RISKS: Risk[] = ["low", "medium", "high"];

interface Props {
  speed: number;
  onSpeed: (kmh: number) => void;
  risk: Risk;
  onRisk: (risk: Risk) => void;
}

export function Settings({ speed, onSpeed, risk, onRisk }: Props) {
  return (
    <div className="settings">
      <label className="speed">
        <span>
          Walking speed <strong>{speed.toFixed(1)} km/h</strong>
        </span>
        <input
          type="range"
          min={3}
          max={8}
          step={0.5}
          value={speed}
          onChange={(e) => onSpeed(Number(e.target.value))}
        />
      </label>
      <div className="risk" role="radiogroup" aria-label="Risk">
        <span>Risk</span>
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
