import { createContext, useContext, type ReactNode } from "react";
import type { AgentId } from "../api/events";
import type { Clause, ProjectInfo } from "../api/client";
import type { RunState } from "./runStore";

/** What the Agent Room components share: the run, the viewer's selections and the reference data. */
export interface RoomValue {
  state: RunState;
  isReplay: boolean;
  /** A replay that stops at the approval gate for the viewer's decision (rather than the recorded one). */
  decisionReplay: boolean;
  speed: number;
  project: ProjectInfo | null;
  contractClauses: Clause[];
  selectedFactId: string | null;
  selectFact: (factId: string | null) => void;
  selectedClause: string | null;
  selectClause: (clauseId: string | null) => void;
  agentFilter: AgentId | null;
  setAgentFilter: (agent: AgentId | null) => void;
  /** Open the trace drawer, optionally showing one tool call. */
  openTrace: (toolCallId?: string | null) => void;
}

/** The viewer's selections only. It changes when the viewer clicks, not with every event, so the many
 * chips in the timeline do not re-render while a run streams. */
export type SelectionValue = Pick<
  RoomValue,
  "selectedFactId" | "selectFact" | "selectedClause" | "selectClause" | "contractClauses"
>;

const RoomContext = createContext<RoomValue | null>(null);
const SelectionContext = createContext<SelectionValue | null>(null);

export function RoomProvider({
  value,
  selection,
  children,
}: {
  value: RoomValue;
  selection: SelectionValue;
  children: ReactNode;
}) {
  return (
    <SelectionContext.Provider value={selection}>
      <RoomContext.Provider value={value}>{children}</RoomContext.Provider>
    </SelectionContext.Provider>
  );
}

export function useRoom(): RoomValue {
  const value = useContext(RoomContext);
  if (!value) throw new Error("useRoom must be used inside RoomProvider");
  return value;
}

export function useSelection(): SelectionValue {
  const value = useContext(SelectionContext);
  if (!value) throw new Error("useSelection must be used inside RoomProvider");
  return value;
}
