/** The seven run stages (SPEC section 10.2), in order. */
export const STAGES = [
  { id: "intake", label: "Intake" },
  { id: "assessment", label: "Assessment" },
  { id: "commercial", label: "Commercial check" },
  { id: "debate", label: "Debate" },
  { id: "synthesis", label: "Synthesis" },
  { id: "approval", label: "Approval" },
  { id: "action", label: "Action" },
] as const;

export type StageId = (typeof STAGES)[number]["id"];
