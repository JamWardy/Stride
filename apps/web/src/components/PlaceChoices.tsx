import type { PlaceChoice } from "../api/client";

interface Props {
  label: string;
  choices: PlaceChoice[];
  onPick: (choice: PlaceChoice) => void;
}

/** TfL's candidates when it can't tell which place was meant. */
export function PlaceChoices({ label, choices, onPick }: Props) {
  return (
    <div className="choices">
      <p>{label}</p>
      <ul>
        {choices.slice(0, 8).map((c) => (
          <li key={c.value}>
            <button type="button" onClick={() => onPick(c)}>
              {c.name}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
