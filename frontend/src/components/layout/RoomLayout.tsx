import { EmptyState, Panel } from "./Panel";

const ANALYSIS_TABS = ["Cost", "Schedule", "Buffer", "Options"] as const;

/** Empty three-column layout: evidence (25%), Agent Room (45%), analysis tabs (30%). */
export function RoomLayout() {
  return (
    <main className="grid min-h-0 flex-1 grid-cols-[25fr_45fr_30fr] gap-4 bg-surface p-4">
      <Panel title="Evidence">
        <EmptyState message="Choose a change to see its instruction, drawings, BOQ (bill of quantities) lines and contract clauses." />
      </Panel>

      <div className="flex min-h-0 flex-col gap-4">
        <Panel title="Agent Room" className="flex-[3]">
          <EmptyState message="The seven agents appear here when a run starts." />
        </Panel>
        <Panel title="Timeline" className="flex-[2]">
          <EmptyState message="Agent messages and tool calls appear here." />
        </Panel>
      </div>

      <Panel title="Analysis">
        <div className="mb-3 flex gap-1" role="tablist" aria-label="Analysis views">
          {ANALYSIS_TABS.map((tab, i) => (
            <button
              key={tab}
              type="button"
              role="tab"
              aria-selected={i === 0}
              disabled
              className={`rounded-full px-3 py-1 text-xs ${i === 0 ? "bg-accent-tint text-accent" : "text-text-muted"}`}
            >
              {tab}
            </button>
          ))}
        </div>
        <EmptyState message="Cost, schedule, buffer and option results appear here." />
      </Panel>
    </main>
  );
}
