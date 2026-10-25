interface TabsProps<T extends string> {
  tabs: readonly T[];
  active: T;
  onChange: (tab: T) => void;
  label: string;
  /** Tabs to mark with a small dot (new content). */
  marked?: readonly T[];
}

/** Pill tabs. */
export function Tabs<T extends string>({ tabs, active, onChange, label, marked = [] }: TabsProps<T>) {
  return (
    <div className="flex gap-1" role="tablist" aria-label={label}>
      {tabs.map((tab) => (
        <button
          key={tab}
          type="button"
          role="tab"
          aria-selected={tab === active}
          onClick={() => onChange(tab)}
          className={`relative rounded-full px-3 py-1 text-xs transition-colors ${
            tab === active ? "bg-accent text-white" : "text-text-muted hover:bg-accent-tint hover:text-accent"
          }`}
        >
          {tab}
          {marked.includes(tab) && tab !== active ? (
            <span className="absolute -top-0.5 -right-0.5 h-2 w-2 rounded-full bg-accent-2" aria-hidden="true" />
          ) : null}
        </button>
      ))}
    </div>
  );
}
