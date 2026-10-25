import { BaseEdge, getStraightPath, type Edge, type EdgeProps } from "@xyflow/react";
import { motion } from "framer-motion";
import type { AgentId } from "../../api/events";
import { AGENTS } from "../../state/agents";

/** A message or question travelling along this edge. `reverse`: from the edge's target to its source. */
export interface EdgeFlight {
  key: string;
  from: AgentId;
  kind: "message" | "ask" | "answer";
  reverse: boolean;
}

export type FlightEdgeData = { flights: EdgeFlight[]; direct: boolean };
export type FlightEdgeType = Edge<FlightEdgeData, "flight">;

const FLIGHT_SECONDS = 1.1;

/** Straight edge between two agents, with animated dots for messages in flight. */
export function FlightEdge({ id, sourceX, sourceY, targetX, targetY, data }: EdgeProps<FlightEdgeType>) {
  const [path] = getStraightPath({ sourceX, sourceY, targetX, targetY });
  const flights = data?.flights ?? [];
  const busy = flights.length > 0;
  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        style={{
          stroke: busy ? "var(--accent-2)" : "var(--border)",
          strokeWidth: busy ? 2 : 1,
          strokeDasharray: data?.direct ? undefined : "4 4",
          transition: "stroke 0.3s",
        }}
      />
      {flights.map((f) => {
        const [x0, y0, x1, y1] = f.reverse ? [targetX, targetY, sourceX, sourceY] : [sourceX, sourceY, targetX, targetY];
        const colour = AGENTS[f.from].colour;
        return (
          <motion.g
            key={f.key}
            initial={{ x: x0, y: y0, opacity: 0 }}
            animate={{ x: [x0, x1], y: [y0, y1], opacity: [1, 1, 0] }}
            transition={{ duration: FLIGHT_SECONDS, ease: "easeInOut", opacity: { times: [0, 0.85, 1], duration: FLIGHT_SECONDS } }}
          >
            {f.kind === "ask" ? (
              <>
                <circle r={9} fill="var(--bg)" stroke={colour} strokeWidth={2} />
                <text textAnchor="middle" dy={4} fontSize={11} fontWeight={700} fill={colour}>
                  ?
                </text>
              </>
            ) : (
              <circle r={f.kind === "answer" ? 5 : 6} fill={colour} stroke="white" strokeWidth={1.5} />
            )}
          </motion.g>
        );
      })}
    </>
  );
}
