import { useMemo, useState } from "react";
import type { OptionsQuery, Risk, Station } from "./api/client";
import { OptionCard } from "./components/OptionCard";
import { Settings } from "./components/Settings";
import { StationSearch } from "./components/StationSearch";
import { useDebounced } from "./hooks/useDebounced";
import { useNow } from "./hooks/useNow";
import { useOptions } from "./hooks/useOptions";
import { useStoredNumber } from "./hooks/useStoredNumber";
import { agoText, shortName } from "./lib/format";

interface Origin {
  lat: number;
  lon: number;
  label: string;
}

export function App() {
  const [origin, setOrigin] = useState<Origin | null>(null);
  const [locating, setLocating] = useState(false);
  const [locateError, setLocateError] = useState<string | null>(null);
  const [speed, setSpeed] = useStoredNumber("walkingSpeedKmh", 5.5);
  const [risk, setRisk] = useState<Risk>("medium");
  const settledSpeed = useDebounced(speed, 400);

  const query = useMemo<OptionsQuery | null>(
    () => origin && { lat: origin.lat, lon: origin.lon, speed_kmh: settledSpeed, risk },
    [origin, settledSpeed, risk],
  );
  const { options, error, loading, updatedAt } = useOptions(query);
  const now = useNow(1000);

  const locateMe = () => {
    if (!("geolocation" in navigator)) {
      setLocateError("This browser can't share your location. Search for a station instead.");
      return;
    }
    setLocating(true);
    setLocateError(null);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLocating(false);
        setOrigin({ lat: pos.coords.latitude, lon: pos.coords.longitude, label: "your location" });
      },
      (err) => {
        setLocating(false);
        setLocateError(`Couldn't get your location (${err.message}). Search for a station instead.`);
      },
      { enableHighAccuracy: true, timeout: 10_000, maximumAge: 15_000 },
    );
  };

  const pickStation = (s: Station) => setOrigin({ lat: s.lat, lon: s.lon, label: shortName(s.name) });

  return (
    <main>
      <header>
        <h1>Walk or wait?</h1>
        <p className="tagline">Trains you can still catch on foot</p>
      </header>

      <section className="where">
        <button type="button" className="locate" onClick={locateMe} disabled={locating}>
          {locating ? "Finding you…" : "Use my location"}
        </button>
        {locateError && <p className="error">{locateError}</p>}
        <StationSearch onSelect={pickStation} />
      </section>

      <Settings speed={speed} onSpeed={setSpeed} risk={risk} onRisk={setRisk} />

      {origin && (
        <section className="results" aria-live="polite">
          <div className="status">
            <span>From {origin.label}</span>
            <span>
              {loading ? "Updating…" : updatedAt !== null ? `Updated ${agoText(now - updatedAt)}` : ""}
            </span>
          </div>
          {error && <p className="error">{error}</p>}
          {options && options.length === 0 && (
            <p className="empty">No catchable trains right now. Try a higher risk setting.</p>
          )}
          {options && options.length > 0 && (
            <ul className="cards">
              {options.map((o) => (
                <OptionCard key={`${o.station_id}|${o.line_id}|${o.direction}`} option={o} />
              ))}
            </ul>
          )}
        </section>
      )}
    </main>
  );
}
