import type { AgentId } from "../api/events";

/** Agent identity (SPEC 12.1): colour, label and icon, never colour alone. */
export interface AgentInfo {
  id: AgentId;
  label: string;
  role: string;
  colour: string;
}

export const AGENTS: Record<AgentId, AgentInfo> = {
  moderator: { id: "moderator", label: "Moderator", role: "Runs the debate and prepares the decision", colour: "var(--agent-moderator)" },
  intake: { id: "intake", label: "Intake", role: "Understands the change", colour: "var(--agent-intake)" },
  contract: { id: "contract", label: "Contract", role: "What the contract allows", colour: "var(--agent-contract)" },
  cost: { id: "cost", label: "Cost", role: "Quantity surveyor: quantities and price", colour: "var(--agent-cost)" },
  time: { id: "time", label: "Time", role: "Planner: programme impact", colour: "var(--agent-time)" },
  commercial: { id: "commercial", label: "Commercial", role: "Buffer, contingency and options", colour: "var(--agent-commercial)" },
  verifier: { id: "verifier", label: "Verifier", role: "Checks every number against the facts", colour: "var(--agent-verifier)" },
};

export const AGENT_IDS: AgentId[] = ["moderator", "intake", "contract", "cost", "time", "commercial", "verifier"];
export const DEBATERS: AgentId[] = ["cost", "time", "commercial"];

export function isAgentId(value: string): value is AgentId {
  return value in AGENTS;
}

export function agentLabel(id: string): string {
  return isAgentId(id) ? AGENTS[id].label : id === "all" ? "everyone" : id;
}
