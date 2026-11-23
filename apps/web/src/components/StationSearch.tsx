import { useEffect, useState } from "react";
import { searchStations, type Station } from "../api/client";
import { shortName } from "../lib/format";
import { useDebounced } from "../hooks/useDebounced";

export function StationSearch({ onSelect }: { onSelect: (station: Station) => void }) {
  const [text, setText] = useState("");
  const query = useDebounced(text.trim(), 300);
  const [results, setResults] = useState<Station[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (query.length < 2) {
      setResults([]);
      return;
    }
    const controller = new AbortController();
    searchStations(query, controller.signal)
      .then((stations) => {
        setResults(stations);
        setError(null);
      })
      .catch((err: unknown) => {
        if (!controller.signal.aborted) setError(err instanceof Error ? err.message : "Search failed");
      });
    return () => controller.abort();
  }, [query]);

  const choose = (station: Station) => {
    onSelect(station);
    setText("");
    setResults([]);
  };

  return (
    <div className="search">
      <label htmlFor="station-search">Or start from a station</label>
      <input
        id="station-search"
        type="search"
        placeholder="e.g. Oxford Circus"
        autoComplete="off"
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
      {error && <p className="error">{error}</p>}
      {results.length > 0 && (
        <ul className="search-results">
          {results.slice(0, 8).map((s) => (
            <li key={s.id}>
              <button type="button" onClick={() => choose(s)}>
                {shortName(s.name)}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
