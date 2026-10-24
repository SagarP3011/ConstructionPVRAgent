import type { ReactNode } from "react";

interface PanelProps {
  title: string;
  children?: ReactNode;
  className?: string;
}

/** Bordered card with a heading, used for every layout area. */
export function Panel({ title, children, className = "" }: PanelProps) {
  return (
    <section className={`flex flex-col rounded-card border border-border bg-bg ${className}`} aria-label={title}>
      <h2 className="border-b border-border px-4 py-3 text-sm">{title}</h2>
      <div className="flex flex-1 flex-col p-4">{children}</div>
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
