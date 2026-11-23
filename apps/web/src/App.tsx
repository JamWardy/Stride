import { Footprints, LocateFixed } from "lucide-react";
import { type FormEvent, useMemo, useState } from "react";
import type { JourneysQuery, PlaceChoice, Risk } from "./api/client";
import { JourneyCard } from "./components/JourneyCard";
import { PlaceChoices } from "./components/PlaceChoices";
import { type Place, PlaceInput } from "./components/PlaceInput";
import { Settings } from "./components/Settings";
import { useDebounced } from "./hooks/useDebounced";
import { useJourneys } from "./hooks/useJourneys";
import { useNow } from "./hooks/useNow";
import { useStoredNumber } from "./hooks/useStoredNumber";
import { agoText } from "./lib/format";

export function App() {
  const [from, setFrom] = useState<Place | null>(null);
  const [to, setTo] = useState<Place | null>(null);
  const [fromText, setFromText] = useState("");
  const [toText, setToText] = useState("");
  const [locating, setLocating] = useState(false);
  const [locateError, setLocateError] = useState<string | null>(null);
  const [speed, setSpeed] = useStoredNumber("walkingSpeedKmh", 5.5);
  const [risk, setRisk] = useState<Risk>("medium");
  const settledSpeed = useDebounced(speed, 400);

  const query = useMemo<JourneysQuery | null>(
    () => (from && to ? { from: from.value, to: to.value, speed_kmh: settledSpeed, risk } : null),
    [from, to, settledSpeed, risk],
  );
  const { data, error, loading, updatedAt } = useJourneys(query);
  const now = useNow(1000);

  const locateMe = () => {
    if (!("geolocation" in navigator)) {
      setLocateError("This browser can't share your location. Type where you are instead.");
      return;
    }
    setLocating(true);
    setLocateError(null);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLocating(false);
        setFromText("");
        setFrom({ label: "Your location", value: `${pos.coords.latitude},${pos.coords.longitude}` });
      },
      (err) => {
        setLocating(false);
        setLocateError(`Couldn't get your location (${err.message}). Type where you are instead.`);
      },
      { enableHighAccuracy: true, timeout: 10_000, maximumAge: 15_000 },
    );
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (fromText.trim()) setFrom({ label: fromText.trim(), value: fromText.trim() });
    if (toText.trim()) setTo({ label: toText.trim(), value: toText.trim() });
  };

  const pick = (set: (p: Place) => void) => (c: PlaceChoice) => set({ label: c.name, value: c.value });

  return (
    <main>
      <header className="brand">
        <span className="tile tile-salmon" aria-hidden="true">
          <Footprints size={22} strokeWidth={2.5} />
        </span>
        <div>
          <h1>
            Walk or <span className="accent">wait?</span>
          </h1>
          <p className="tagline">Door to door, at your walking speed</p>
        </div>
      </header>

      <section className="panel">
        <form className="where" onSubmit={submit}>
          <div className="from">
            <PlaceInput
              id="from"
              label="From"
              placeholder={from ? from.label : "A place, postcode or station"}
              text={fromText}
              onText={setFromText}
              onSelect={setFrom}
            />
            <button type="button" className="btn btn-secondary locate" onClick={locateMe} disabled={locating}>
              <LocateFixed size={18} strokeWidth={2.5} aria-hidden="true" />
              {locating ? "Finding you…" : "Use my location"}
            </button>
            {locateError && <p className="error">{locateError}</p>}
          </div>
          <PlaceInput
            id="to"
            label="Where to?"
            placeholder={to ? to.label : "e.g. Oxford Circus"}
            text={toText}
            onText={setToText}
            onSelect={setTo}
          />
          <button type="submit" className="btn btn-primary">
            Go
          </button>
        </form>

        <Settings speed={speed} onSpeed={setSpeed} risk={risk} onRisk={setRisk} />
      </section>

      {to && !from && <p className="empty">Where are you starting from? Use your location or type a place.</p>}

      {query && (
        <section className="results" aria-live="polite">
          <div className="status">
            <span className="route">
              {from?.label} → {to?.label}
            </span>
            <span>{loading ? "Updating…" : updatedAt !== null ? `Updated ${agoText(now - updatedAt)}` : ""}</span>
          </div>
          {error && <p className="error">{error}</p>}
          {data?.kind === "ambiguous" && (
            <>
              {data.from_options.length > 0 && (
                <PlaceChoices label="Which start did you mean?" choices={data.from_options} onPick={pick(setFrom)} />
              )}
              {data.to_options.length > 0 && (
                <PlaceChoices label="Where did you mean?" choices={data.to_options} onPick={pick(setTo)} />
              )}
            </>
          )}
          {data?.kind === "journeys" && data.journeys.length === 0 && (
            <p className="empty">No routes found right now.</p>
          )}
          {data?.kind === "journeys" && data.journeys.length > 0 && (
            <ul className="cards">
              {data.journeys.map((j, i) => (
                <JourneyCard key={`${j.arrival_time}-${i}`} journey={j} now={now} />
              ))}
            </ul>
          )}
        </section>
      )}
    </main>
  );
}
