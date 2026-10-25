import { useEffect, useRef, useState } from "react";
import { useRoom } from "../../state/RoomContext";
import { Tabs } from "../common/Tabs";
import { Panel } from "../layout/Panel";
import { BufferPanel } from "./BufferPanel";
import { CostPanel } from "./CostPanel";
import { GanttPanel } from "./GanttPanel";
import { OptionsPanel } from "./OptionsPanel";

const TABS = ["Cost", "Schedule", "Buffer", "Options"] as const;
type Tab = (typeof TABS)[number];

/** Right column: cost, schedule, buffer and options, each filled from tool results as they arrive. */
export function AnalysisPanel() {
  const { state } = useRoom();
  const [tab, setTab] = useState<Tab>("Cost");
  const [marked, setMarked] = useState<Tab[]>([]);
  const r = state.results;
  const hasContent: Record<Tab, boolean> = {
    Cost: Boolean(r.price),
    Schedule: Boolean(r.impactedCpm || r.addedDuration),
    Buffer: Object.keys(r.buffers).length > 0 || Boolean(state.finalOptions),
    Options: Object.keys(state.options).length > 0,
  };
  const previous = useRef(hasContent);

  // Mark a tab when its content first appears, so the viewer sees where something new is.
  useEffect(() => {
    const fresh = TABS.filter((t) => hasContent[t] && !previous.current[t]);
    previous.current = hasContent;
    if (fresh.length) setMarked((old) => [...new Set([...old, ...fresh])]);
  });

  const choose = (t: Tab) => {
    setTab(t);
    setMarked((old) => old.filter((x) => x !== t));
  };

  return (
    <Panel title="Analysis" right={<Tabs tabs={TABS} active={tab} onChange={choose} label="Analysis views" marked={marked} />}>
      {tab === "Cost" ? <CostPanel /> : null}
      {tab === "Schedule" ? <GanttPanel /> : null}
      {tab === "Buffer" ? <BufferPanel /> : null}
      {tab === "Options" ? <OptionsPanel /> : null}
    </Panel>
  );
}
