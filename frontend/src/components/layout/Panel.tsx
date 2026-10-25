import type { ReactNode } from "react";

interface PanelProps {
  title: string;
  children?: ReactNode;
  className?: string;
  /** Content on the right of the heading (tabs, counts, buttons). */
  right?: ReactNode;
  /** Body padding; off for content that draws edge to edge (graphs). */
  padded?: boolean;
  /** The body scrolls; off for content that manages its own scrolling (the timeline, the graph). */
  scroll?: boolean;
}

/** Bordered card with a heading, used for every layout area. The body scrolls. */
export function Panel({ title, children, className = "", right, padded = true, scroll = true }: PanelProps) {
  return (
    <section
      className={`flex min-h-0 flex-col rounded-card border border-border bg-bg ${className}`}
      aria-label={title}
    >
      <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-2.5">
        <h2 className="text-sm">{title}</h2>
        {right}
      </div>
      <div className={`flex min-h-0 flex-1 flex-col ${scroll ? "overflow-y-auto" : "overflow-hidden"} ${padded ? "p-4" : ""}`}>
        {children}
      </div>
    </section>
  );
}

/** Placeholder shown while a panel has nothing to display. */
export function EmptyState({ message }: { message: string }) {
  return (
    <div className="flex flex-1 items-center justify-center rounded-card bg-surface p-6 text-center text-sm text-text-muted">
      {message}
    </div>
  );
}

/** Placeholder while an agent is working on what the panel will show. */
export function LoadingState({ message }: { message: string }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-3 rounded-card bg-surface p-6 text-center text-sm text-text-muted">
      <span className="flex gap-1" aria-hidden="true">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="h-1.5 w-1.5 animate-bounce rounded-full bg-accent-2"
            style={{ animationDelay: `${i * 0.15}s` }}
          />
        ))}
      </span>
      {message}
    </div>
  );
}

/** Error message for a panel. */
export function ErrorState({ message }: { message: string }) {
  return (
    <div className="rounded-card border border-alert bg-bg p-3 text-sm text-alert" role="alert">
      {message}
    </div>
  );
}
