import { useState } from "react";
import { api, type Interpretation } from "../../api/client";
import { ErrorState } from "../layout/Panel";

const EXAMPLES = [
  "Make the boundary wall half a metre higher",
  "We need a drop-off lane: widen the internal road by one and a half metres over 800 m",
  "Extend the plaza with another 600 m2 of interlocking paving",
];

interface FreeTextRequestProps {
  liveAvailable: boolean | null;
  /** The person confirms the reading: the selector takes over the change, sizes and mode. */
  onUse: (reading: Interpretation) => void;
}

/** Type a change in your own words; the Intake agent reads it as one of the supported changes. */
export function FreeTextRequest({ liveAvailable, onUse }: FreeTextRequestProps) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reading, setReading] = useState<Interpretation | null>(null);

  const interpret = async () => {
    setBusy(true);
    setError(null);
    setReading(null);
    try {
      setReading(await api.interpret(text));
    } catch (e) {
      setError(e instanceof Error ? e.message : "The request could not be read");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mb-4 flex flex-col gap-2 rounded-card bg-surface p-4" aria-label="Describe the change">
      <label htmlFor="free-text" className="text-sm font-semibold">
        Describe the change in your own words
      </label>
      <div className="flex gap-2">
        <input
          id="free-text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && text.trim() && !busy) void interpret();
          }}
          maxLength={500}
          placeholder={`For example: ${EXAMPLES[0]}`}
          className="flex-1 rounded border border-border bg-bg px-3 py-2 text-sm"
        />
        <button
          type="button"
          onClick={() => void interpret()}
          disabled={!text.trim() || busy || liveAvailable === false}
          className="rounded-full bg-accent px-4 py-2 text-sm font-semibold text-white disabled:opacity-40"
        >
          {busy ? "Reading…" : "Read my request"}
        </button>
      </div>
      <p className="text-xs text-text-muted">
        The Intake agent matches it to one of the three changes below and their allowed sizes, then you confirm.
        {liveAvailable === false ? " Needs an OpenAI API key; choose a change below instead." : ""}
      </p>
      {error ? <ErrorState message={error} /> : null}
      {reading?.status === "declined" ? (
        <div className="rounded-card border border-border bg-bg p-3 text-sm" role="status">
          <span className="font-semibold text-accent">The Intake agent cannot assess this here.</span> {reading.reason}
        </div>
      ) : null}
      {reading?.status === "interpreted" ? (
        <div className="flex flex-col gap-2 rounded-card border border-accent-2 bg-bg p-3 text-sm" role="status">
          <div>
            <span className="font-semibold text-accent">{reading.title}</span>
            {reading.reading ? <span className="text-text-muted"> · {reading.reading}</span> : null}
          </div>
          <p>{reading.instruction_text}</p>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => {
                onUse(reading);
                setReading(null);
              }}
              className="rounded-full bg-accent px-4 py-1.5 text-xs font-semibold text-white"
            >
              Yes, use this
            </button>
            <button
              type="button"
              onClick={() => setReading(null)}
              className="rounded-full px-3 py-1.5 text-xs text-text-muted hover:text-accent"
            >
              Not what I meant
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
