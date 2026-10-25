import type { AgentId } from "../../api/events";
import { AGENTS } from "../../state/agents";

/** Simple line icons for each agent (SPEC 12.1 icon ideas). */
const PATHS: Record<AgentId, string> = {
  // gavel
  moderator: "M14 4l6 6M11 7l6 6M12.5 5.5l-5 5 3 3 5-5M8.5 12.5L3 18l3 3 5.5-5.5M13 21h8",
  // inbox
  intake: "M3 13h5l1.5 3h5L16 13h5M5 5h14l2 8v6H3v-6z",
  // document with seal
  contract: "M6 3h9l4 4v6M6 3v18h7M9 8h6M9 12h6M17 17m-3 0a3 3 0 1 0 6 0a3 3 0 1 0-6 0M15.5 19.5L15 23l2-1 2 1-.5-3.5",
  // calculator
  cost: "M6 3h12v18H6zM9 6h6v3H9zM9 13h.01M12 13h.01M15 13h.01M9 17h.01M12 17h.01M15 17h.01",
  // clock
  time: "M12 12m-9 0a9 9 0 1 0 18 0a9 9 0 1 0-18 0M12 7v5l3 2",
  // scale
  commercial: "M12 4v16M7 20h10M5 7h14M5 7l-3 6h6zM19 7l-3 6h6zM12 4l-1 1",
  // shield with check
  verifier: "M12 3l8 3v6c0 4.5-3.4 8.3-8 9-4.6-.7-8-4.5-8-9V6zM8.5 12l2.5 2.5 4.5-5",
};

interface AgentIconProps {
  agent: AgentId;
  size?: number;
  className?: string;
}

export function AgentIcon({ agent, size = 18, className = "" }: AgentIconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.7}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <path d={PATHS[agent]} />
    </svg>
  );
}

/** Icon plus label in the agent's colour. */
export function AgentTag({ agent, size = 14 }: { agent: AgentId; size?: number }) {
  const info = AGENTS[agent];
  return (
    <span className="inline-flex items-center gap-1 font-semibold" style={{ color: info.colour }}>
      <AgentIcon agent={agent} size={size} />
      {info.label}
    </span>
  );
}
