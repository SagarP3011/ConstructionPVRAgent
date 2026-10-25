import { useEffect, useRef } from "react";
import type { StartRunBody } from "../../api/client";
import { useRoom } from "../../state/RoomContext";
import { DetailDrawer } from "../common/DetailDrawer";
import { DecisionPanel } from "../decision/DecisionPanel";
import { EvidencePanel } from "../evidence/EvidencePanel";
import { OutputsPanel } from "../outputs/OutputsPanel";
import { AnalysisPanel } from "../panels/AnalysisPanel";
import { AgentGraph } from "../room/AgentGraph";
import { Timeline } from "../room/Timeline";
import { TraceDrawer } from "../trace/TraceDrawer";
import { WhatIfControls } from "../whatif/WhatIfControls";
import type { RoomView } from "./Header";
import { ErrorState, Panel } from "./Panel";
import { StageCaption } from "./StageCaption";

const ROOM_HINT = "Each circle is an agent; it lights up while it works. Lines show who is talking to whom.";
const TIMELINE_HINT = "Every message and tool call, in order. Click a fact id such as F-0012 to see where a number came from.";

interface RoomLayoutProps {
  connectionError: string | null;
  liveAvailable: boolean | null;
  onRerun: (request: StartRunBody) => Promise<void>;
  trace: { open: boolean; focusToolCall: string | null; close: () => void; clearFocus: () => void };
  /** Simple: the agents, what is happening now and the decision. Details: everything. */
  view: RoomView;
}

/** The run screen. Details view: evidence (25%), Agent Room (45%), analysis tabs (30%). Simple view: the
 * Agent Room and the timeline only. Both: a caption for the current stage on top, decision and outputs below. */
export function RoomLayout({ connectionError, liveAvailable, onRerun, trace, view }: RoomLayoutProps) {
  const { state, isReplay, decisionReplay } = useRoom();
  const decision = useRef<HTMLDivElement>(null);
  const fatal = state.errors.find((e) => e.fatal);
  // Errors that did not stop the run (for example an execution attempted before approval).
  const agentErrors = state.errors.filter((e) => !e.fatal);

  // Bring the decision into view when the run asks for approval.
  useEffect(() => {
    if (state.approvalRequested) decision.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [state.approvalRequested]);

  return (
    <main className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto bg-surface p-4">
      <StageCaption state={state} recordedDecision={isReplay && !decisionReplay} />
      {view === "details" ? <WhatIfControls liveAvailable={liveAvailable} onRerun={onRerun} /> : null}
      {connectionError ? <ErrorState message={connectionError} /> : null}
      {fatal ? <ErrorState message={`The run stopped${fatal.stage ? ` during ${fatal.stage}` : ""}: ${fatal.error}`} /> : null}
      {!fatal && agentErrors.length ? (
        <ErrorState
          message={`${agentErrors.length} agent error${agentErrors.length === 1 ? "" : "s"} in this run. Latest${
            agentErrors[agentErrors.length - 1]?.agent ? ` (${agentErrors[agentErrors.length - 1]?.agent})` : ""
          }: ${agentErrors[agentErrors.length - 1]?.error ?? ""}`}
        />
      ) : null}

      {view === "simple" ? (
        <div className="grid h-[calc(100vh-190px)] min-h-[560px] shrink-0 grid-cols-[minmax(0,3fr)_minmax(0,2fr)] gap-4">
          <Panel
            title="Agent Room"
            hint={ROOM_HINT}
            padded={false}
            scroll={false}
            right={<span className="text-[11px] text-text-muted">Click an agent to follow it</span>}
          >
            <AgentGraph />
          </Panel>
          <Panel title="Timeline" hint={TIMELINE_HINT} padded={false} scroll={false}>
            <Timeline />
          </Panel>
        </div>
      ) : (
      <div className="grid h-[calc(100vh-120px)] min-h-[620px] shrink-0 grid-cols-[minmax(0,25fr)_minmax(0,45fr)_minmax(0,30fr)] gap-4">
        <EvidencePanel />

        <div className="flex min-h-0 flex-col gap-4">
          <Panel
            title="Agent Room"
            hint={ROOM_HINT}
            className="h-[44%] min-h-[280px] shrink-0"
            padded={false}
            scroll={false}
            right={<span className="text-[11px] text-text-muted">Click an agent to follow it</span>}
          >
            <AgentGraph />
          </Panel>
          <Panel title="Timeline" hint={TIMELINE_HINT} className="flex-1" padded={false} scroll={false}>
            <Timeline />
          </Panel>
        </div>

        <AnalysisPanel />
      </div>
      )}

      <div ref={decision} className="flex shrink-0 flex-col gap-4">
        <DecisionPanel />
        <OutputsPanel />
      </div>

      <p className="shrink-0 text-center text-[11px] text-text-muted">
        The orchestrator fixes the stages. Inside each stage the agents choose their own tools, questions and
        positions. Every number comes from a deterministic engine through a tool; nothing runs until a person approves.
      </p>

      <DetailDrawer />
      <TraceDrawer
        open={trace.open}
        focusToolCall={trace.focusToolCall}
        onClose={trace.close}
        onClearFocus={trace.clearFocus}
      />
    </main>
  );
}
