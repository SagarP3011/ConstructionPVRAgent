import { useEffect, useRef } from "react";
import { useRoom } from "../../state/RoomContext";
import { DetailDrawer } from "../common/DetailDrawer";
import { DecisionPanel } from "../decision/DecisionPanel";
import { EvidencePanel } from "../evidence/EvidencePanel";
import { OutputsPanel } from "../outputs/OutputsPanel";
import { AnalysisPanel } from "../panels/AnalysisPanel";
import { AgentGraph } from "../room/AgentGraph";
import { Timeline } from "../room/Timeline";
import { ErrorState, Panel } from "./Panel";

interface RoomLayoutProps {
  connectionError: string | null;
}

/** The run screen: evidence (25%), Agent Room (45%), analysis tabs (30%); decision and outputs below. */
export function RoomLayout({ connectionError }: RoomLayoutProps) {
  const { state } = useRoom();
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
      {connectionError ? <ErrorState message={connectionError} /> : null}
      {fatal ? <ErrorState message={`The run stopped${fatal.stage ? ` during ${fatal.stage}` : ""}: ${fatal.error}`} /> : null}
      {!fatal && agentErrors.length ? (
        <ErrorState
          message={`${agentErrors.length} agent error${agentErrors.length === 1 ? "" : "s"} in this run. Latest${
            agentErrors[agentErrors.length - 1]?.agent ? ` (${agentErrors[agentErrors.length - 1]?.agent})` : ""
          }: ${agentErrors[agentErrors.length - 1]?.error ?? ""}`}
        />
      ) : null}

      <div className="grid h-[calc(100vh-120px)] min-h-[620px] shrink-0 grid-cols-[minmax(0,25fr)_minmax(0,45fr)_minmax(0,30fr)] gap-4">
        <EvidencePanel />

        <div className="flex min-h-0 flex-col gap-4">
          <Panel
            title="Agent Room"
            className="h-[44%] min-h-[280px] shrink-0"
            padded={false}
            scroll={false}
            right={<span className="text-[11px] text-text-muted">Click an agent to follow it</span>}
          >
            <AgentGraph />
          </Panel>
          <Panel title="Timeline" className="flex-1" padded={false} scroll={false}>
            <Timeline />
          </Panel>
        </div>

        <AnalysisPanel />
      </div>

      <div ref={decision} className="flex shrink-0 flex-col gap-4">
        <DecisionPanel />
        <OutputsPanel />
      </div>

      <p className="shrink-0 text-center text-[11px] text-text-muted">
        The orchestrator fixes the stages. Inside each stage the agents choose their own tools, questions and
        positions. Every number comes from a deterministic engine through a tool; nothing runs until a person approves.
      </p>

      <DetailDrawer />
    </main>
  );
}
