import { STAGES, type StageId } from "./stages";

interface StageProgressProps {
  /** The stage in progress, or null before a run starts. */
  current: StageId | null;
}

/** Seven-step progress bar for the run stages. */
export function StageProgress({ current }: StageProgressProps) {
  const currentIndex = current ? STAGES.findIndex((s) => s.id === current) : -1;
  return (
    <ol className="flex gap-1" aria-label="Run stages">
      {STAGES.map((stage, index) => {
        const state = index < currentIndex ? "done" : index === currentIndex ? "active" : "pending";
        const bar = state === "done" ? "bg-accent" : state === "active" ? "bg-accent-2" : "bg-surface-2";
        return (
          <li
            key={stage.id}
            className="flex w-24 flex-col gap-1"
            aria-current={state === "active" ? "step" : undefined}
          >
            <span className={`h-1.5 rounded-full ${bar}`} />
            <span className={`text-[11px] ${state === "pending" ? "text-text-muted" : "text-accent"}`}>
              {stage.label}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
