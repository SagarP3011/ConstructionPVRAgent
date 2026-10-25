import { CHANGE_LABEL } from "../../format";
import type { RunContext } from "../../api/events";
import { StageProgress } from "./StageProgress";
import type { StageId } from "./stages";

export type BackendState = "checking" | "connected" | "unreachable";

const BACKEND_LABEL: Record<BackendState, string> = {
  checking: "Checking backend",
  connected: "Backend connected",
  unreachable: "Backend not reachable",
};

const BACKEND_DOT: Record<BackendState, string> = {
  checking: "bg-border",
  connected: "bg-accent-2",
  unreachable: "bg-alert",
};

export const SPEEDS = [0.5, 1, 2] as const;

export type RoomView = "simple" | "details";

interface HeaderProps {
  backend: BackendState;
  context: RunContext | null;
  stage: StageId | null;
  stagesDone: string[];
  /** "replay" while a recording plays; "decide" when it pauses for the viewer's decision. */
  replay: "replay" | "decide" | null;
  speed: number;
  view: RoomView;
  onView: (view: RoomView) => void;
  onGuide: () => void;
  onSpeed: (speed: number) => void;
  onNewChange: (() => void) | null;
  onTrace: (() => void) | null;
}

/** App header: title, notice, the current change, stage progress, speed control and New change. */
export function Header({
  backend,
  context,
  stage,
  stagesDone,
  replay,
  speed,
  view,
  onView,
  onGuide,
  onSpeed,
  onNewChange,
  onTrace,
}: HeaderProps) {
  return (
    <header className="flex items-center justify-between gap-6 border-b border-border bg-bg px-6 py-3">
      <div className="min-w-0">
        <h1 className="text-xl">PVR Agent Room</h1>
        <p className="text-xs text-text-muted">Proof of concept by Sekuen, prepared for Aldar. Illustrative data.</p>
        {context ? (
          <p className="mt-0.5 truncate text-xs font-semibold text-accent">
            {CHANGE_LABEL[context.change_type] ?? context.change_type}:{" "}
            {Object.entries(context.parameters)
              .map(([k, v]) => `${k.replace(/_/g, " ")} ${v}`)
              .join(", ")}{" "}
            · {context.mode === "contractor_pvr" ? "contractor PVR (potential variation request)" : "internal what-if"}
            {replay === "decide" ? " · replay of a saved run, you decide" : replay ? " · replay" : ""}
          </p>
        ) : null}
      </div>

      <StageProgress current={stage} done={stagesDone} />

      <div className="flex shrink-0 items-center gap-4">
        {context ? (
          <div className="flex items-center gap-1 text-xs" role="group" aria-label="Speed">
            <span className="mr-1 text-text-muted">Speed</span>
            {SPEEDS.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => onSpeed(s)}
                aria-pressed={speed === s}
                className={`rounded-full px-2 py-0.5 ${speed === s ? "bg-accent text-white" : "text-text-muted hover:text-accent"}`}
              >
                {s}x
              </button>
            ))}
          </div>
        ) : null}
        {context ? (
          <button
            type="button"
            onClick={() => onView(view === "simple" ? "details" : "simple")}
            aria-pressed={view === "details"}
            className="rounded-full border border-accent px-3 py-1.5 text-xs font-semibold text-accent hover:bg-accent-tint"
          >
            {view === "simple" ? "Show details" : "Simple view"}
          </button>
        ) : null}
        {onTrace ? (
          <button
            type="button"
            onClick={onTrace}
            className="rounded-full px-3 py-1.5 text-xs font-semibold text-accent hover:bg-accent-tint"
          >
            Trace
          </button>
        ) : null}
        {onNewChange ? (
          <button
            type="button"
            onClick={onNewChange}
            className="rounded-full border border-accent px-4 py-1.5 text-xs font-semibold text-accent hover:bg-accent hover:text-white"
          >
            New change
          </button>
        ) : null}
        <button
          type="button"
          onClick={onGuide}
          aria-label="What am I looking at?"
          title="What am I looking at?"
          className="flex h-7 w-7 items-center justify-center rounded-full border border-accent text-sm font-semibold text-accent hover:bg-accent hover:text-white"
        >
          ?
        </button>
        <div className="flex items-center gap-2 text-xs text-text-muted" role="status">
          <span className={`h-2 w-2 rounded-full ${BACKEND_DOT[backend]}`} aria-hidden="true" />
          {BACKEND_LABEL[backend]}
        </div>
      </div>
    </header>
  );
}
