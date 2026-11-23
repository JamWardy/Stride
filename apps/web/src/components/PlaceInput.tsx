import { useEffect, useRef, useState } from "react";
import { newSessionToken, resolvePlace, suggestPlaces, type Suggestion } from "../api/client";
import { useDebounced } from "../hooks/useDebounced";
import { shortName } from "../lib/format";

/** A start or destination: what to show, and what to send to the API. */
export interface Place {
  label: string;
  value: string;
}

interface Props {
  id: string;
  label: string;
  placeholder: string;
  text: string;
  onText: (text: string) => void;
  onSelect: (place: Place) => void;
}

/** A text box with type-ahead: stations first, then Google's places. */
export function PlaceInput({ id, label, placeholder, text, onText, onSelect }: Props) {
  const query = useDebounced(text.trim(), 250);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [error, setError] = useState<string | null>(null);
  const session = useRef(newSessionToken());

  useEffect(() => {
    if (query.length < 2) {
      setSuggestions([]);
      return;
    }
    const controller = new AbortController();
    suggestPlaces(query, session.current, controller.signal)
      .then((found) => {
        setSuggestions(found);
        setError(null);
      })
      .catch((err: unknown) => {
        if (!controller.signal.aborted) setError(err instanceof Error ? err.message : "Search failed");
      });
    return () => controller.abort();
  }, [query]);

  const choose = async (s: Suggestion) => {
    setSuggestions([]);
    onText("");
    try {
      if (s.kind === "station") {
        onSelect({ label: shortName(s.name), value: s.value });
      } else {
        onSelect({ label: s.name, value: await resolvePlace(s.place_id, session.current) });
      }
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't find that place");
    } finally {
      session.current = newSessionToken(); // the next search is a new session
    }
  };

  return (
    <div className="place-input">
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        type="search"
        placeholder={placeholder}
        autoComplete="off"
        value={text}
        onChange={(e) => onText(e.target.value)}
      />
      {error && <p className="error">{error}</p>}
      {suggestions.length > 0 && (
        <ul className="suggestions">
          {suggestions.map((s) => (
            <li key={s.kind === "station" ? `s-${s.value}` : `p-${s.place_id}`}>
              <button type="button" onClick={() => void choose(s)}>
                <span className="suggestion-name">{s.kind === "station" ? shortName(s.name) : s.name}</span>
                <span className="suggestion-detail">{s.kind === "station" ? "Station" : s.detail}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
