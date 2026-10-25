import { applyNodeChanges, ReactFlow, ReactFlowProvider, type NodeChange, type NodeMouseHandler } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { AgentId } from "../../api/events";
import { AGENT_IDS, DEBATERS } from "../../state/agents";
import type { Flight } from "../../state/runStore";
import { useRoom } from "../../state/RoomContext";
import { AgentNode, type AgentNodeType } from "./AgentNode";
import { FlightEdge, type EdgeFlight, type FlightEdgeType } from "./FlightEdge";

/** Agents around the Moderator, on an ellipse that suits a wide panel. */
const POSITIONS: Record<AgentId, { x: number; y: number }> = (() => {
  const ring: AgentId[] = ["intake", "contract", "cost", "commercial", "time", "verifier"];
  const out = { moderator: { x: 0, y: 0 } } as Record<AgentId, { x: number; y: number }>;
  ring.forEach((agent, i) => {
    const angle = -Math.PI / 2 + (i * 2 * Math.PI) / ring.length;
    out[agent] = { x: Math.round(290 * Math.cos(angle)), y: Math.round(125 * Math.sin(angle)) };
  });
  return out;
})();

const nodeTypes = { agent: AgentNode };
const edgeTypes = { flight: FlightEdge };
const FLIGHT_VISIBLE_MS = 1300;
const MAX_NEW_FLIGHTS = 6;

interface ActiveFlight extends Flight {
  key: string;
}

function pairId(a: AgentId, b: AgentId): string {
  return [a, b].sort().join("~");
}

/** Which edge a flight travels on, and in which direction. */
function route(f: Flight): { edge: string; reverse: boolean }[] {
  const spoke = (agent: AgentId, outward: boolean) => ({ edge: `spoke-${agent}`, reverse: !outward });
  if (f.to === "all") {
    if (f.from === "moderator") return AGENT_IDS.filter((a) => a !== "moderator").map((a) => spoke(a, true));
    return [spoke(f.from, false)];
  }
  if (f.from === "moderator") return [spoke(f.to, true)];
  if (f.to === "moderator") return [spoke(f.from, false)];
  const [a] = [f.from, f.to].sort() as [AgentId, AgentId];
  return [{ edge: `pair-${pairId(f.from, f.to)}`, reverse: f.from !== a }];
}

function Graph() {
  const { state, agentFilter, setAgentFilter } = useRoom();
  const [active, setActive] = useState<ActiveFlight[]>([]);
  const lastSeq = useRef(0);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);

  // Animate flights that arrived since the last update (the newest few after a burst or a jump).
  useEffect(() => {
    const fresh = state.flights.filter((f) => f.seq > lastSeq.current).slice(-MAX_NEW_FLIGHTS);
    if (state.flights.length) lastSeq.current = Math.max(lastSeq.current, ...state.flights.map((f) => f.seq));
    if (fresh.length === 0) return;
    const added = fresh.map((f) => ({ ...f, key: `${f.seq}-${f.from}-${f.to}` }));
    setActive((old) => [...old, ...added]);
    timers.current.push(
      setTimeout(() => setActive((old) => old.filter((f) => !added.some((a) => a.key === f.key))), FLIGHT_VISIBLE_MS),
    );
  }, [state.flights]);

  useEffect(() => () => timers.current.forEach(clearTimeout), []);

  // A new run starts with no flights.
  useEffect(() => {
    if (state.seq === 0) {
      lastSeq.current = 0;
      setActive([]);
    }
  }, [state.seq]);

  const showStance = state.stagesDone.includes("assessment") || DEBATERS.some((a) => state.agents[a].stance);

  // Nodes live in state so React Flow can record their measured size; only their data follows the run.
  const [nodes, setNodes] = useState<AgentNodeType[]>(() =>
    AGENT_IDS.map((agent) => ({
      id: agent,
      type: "agent" as const,
      position: POSITIONS[agent],
      draggable: false,
      selectable: false,
      data: { agent, view: state.agents[agent], selected: false, dimmed: false, showStance: false },
    })),
  );
  useEffect(() => {
    setNodes((old) =>
      old.map((node) => {
        const agent = node.data.agent;
        const data = {
          agent,
          view: state.agents[agent],
          selected: agentFilter === agent,
          dimmed: agentFilter !== null && agentFilter !== agent,
          showStance: showStance && DEBATERS.includes(agent),
        };
        const d = node.data;
        const same = d.view === data.view && d.selected === data.selected && d.dimmed === data.dimmed && d.showStance === data.showStance;
        return same ? node : { ...node, data };
      }),
    );
  }, [state.agents, agentFilter, showStance]);
  const onNodesChange = useCallback(
    (changes: NodeChange<AgentNodeType>[]) => setNodes((old) => applyNodeChanges(changes, old)),
    [],
  );

  // Direct conversations between agents (other than with the Moderator) get their own edge.
  const pairs = useMemo(() => {
    const found = new Map<string, [AgentId, AgentId]>();
    for (const m of Object.values(state.messages)) {
      if (m.to !== "all" && m.to !== "moderator" && m.from !== "moderator" && m.from !== m.to) {
        found.set(pairId(m.from, m.to), [m.from, m.to].sort() as [AgentId, AgentId]);
      }
    }
    return [...found.entries()];
  }, [state.messages]);

  const edges: FlightEdgeType[] = useMemo(() => {
    const byEdge = new Map<string, EdgeFlight[]>();
    for (const f of active) {
      for (const r of route(f)) {
        const list = byEdge.get(r.edge) ?? [];
        list.push({ key: `${f.key}-${r.edge}`, from: f.from, kind: f.kind, reverse: r.reverse });
        byEdge.set(r.edge, list);
      }
    }
    const spokes = AGENT_IDS.filter((a) => a !== "moderator").map((agent) => ({
      id: `spoke-${agent}`,
      source: "moderator",
      target: agent,
      type: "flight" as const,
      data: { flights: byEdge.get(`spoke-${agent}`) ?? [], direct: false },
    }));
    const direct = pairs.map(([id, [a, b]]) => ({
      id: `pair-${id}`,
      source: a,
      target: b,
      type: "flight" as const,
      data: { flights: byEdge.get(`pair-${id}`) ?? [], direct: true },
    }));
    return [...spokes, ...direct];
  }, [active, pairs]);

  const onNodeClick: NodeMouseHandler<AgentNodeType> = (_, node) => {
    const agent = node.id as AgentId;
    setAgentFilter(agentFilter === agent ? null : agent);
  };

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      onNodesChange={onNodesChange}
      nodeTypes={nodeTypes}
      edgeTypes={edgeTypes}
      onNodeClick={onNodeClick}
      fitView
      fitViewOptions={{ padding: 0.12 }}
      nodesDraggable={false}
      nodesConnectable={false}
      elementsSelectable={false}
      panOnDrag={false}
      zoomOnScroll={false}
      zoomOnPinch={false}
      zoomOnDoubleClick={false}
      preventScrolling={false}
    />
  );
}

/** The Agent Room: seven agents, live activity, messages and questions flying between them. */
export function AgentGraph() {
  return (
    <div className="h-full w-full" aria-label="Agent Room graph">
      <ReactFlowProvider>
        <Graph />
      </ReactFlowProvider>
    </div>
  );
}
