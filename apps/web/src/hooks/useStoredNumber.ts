import { useEffect, useState } from "react";

/** A number remembered in localStorage across visits. */
export function useStoredNumber(key: string, fallback: number): [number, (value: number) => void] {
  const [value, setValue] = useState(() => {
    const stored = Number(localStorage.getItem(key));
    return localStorage.getItem(key) !== null && Number.isFinite(stored) ? stored : fallback;
  });
  useEffect(() => {
    localStorage.setItem(key, String(value));
  }, [key, value]);
  return [value, setValue];
}
