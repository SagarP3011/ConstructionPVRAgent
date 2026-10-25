import type { RunState } from "../../state/runStore";

export interface Caption {
  title: string;
  text: string;
}

const STAGE_CAPTION: Record<string, Caption> = {
  intake: {
    title: "Reading the change",
    text: "The Intake agent reads the change request, compares the drawing revisions and checks the notice. It then shares the evidence with the team.",
  },
  assessment: {
    title: "The specialists assess the change",
    text: "The Contract, Cost and Time agents each work out their part with calculation tools: what the contract allows, the quantities and price, and the effect on the programme. They can ask each other questions.",
  },
  commercial: {
    title: "Checking the options against the budget and the programme",
    text: "The Commercial agent lists the ways to deliver the change and checks each one against the remaining cost contingency and the time buffer.",
  },
  debate: {
    title: "The agents debate the options",
    text: "The Cost, Time and Commercial agents argue for the option they prefer. An agent changes its mind only when another gives a reason backed by facts.",
  },
  synthesis: {
    title: "Preparing the decision",
    text: "The Moderator sums up the debate, picks the options worth choosing between and proposes the actions to take after approval.",
  },
  approval: {
    title: "Waiting for a person to decide",
    text: "The agents have finished. Nothing happens until a named person chooses an option and approves it below.",
  },
  action: {
    title: "Carrying out the approved actions",
    text: "The approved option is recorded and the approved documents are drafted. This step is code only, with no AI.",
  },
};

/** A plain-English sentence for where the run is now, for people watching the screen. */
export function captionFor(state: RunState, recordedDecision: boolean): Caption | null {
  if (state.status === "failed") {
    return { title: "The run stopped", text: "Something went wrong; the message above says what. Nothing was executed." };
  }
  if (state.status === "completed") {
    return {
      title: "Done: approved and recorded",
      text: "A person approved an option. The documents they approved are in Outputs below, and every step is in the Trace.",
    };
  }
  if (state.status === "rejected") {
    return { title: "Rejected", text: "A person rejected the assessment with a reason. Nothing was executed." };
  }
  if (state.status === "awaiting_approval" && !state.decision) {
    return recordedDecision
      ? { title: "The recorded decision follows", text: "This replay includes the decision taken when it was recorded." }
      : STAGE_CAPTION.approval ?? null;
  }
  return state.stage ? STAGE_CAPTION[state.stage] ?? null : { title: "Starting", text: "The run is starting." };
}

/** A banner under the header: what is happening now, in plain English. */
export function StageCaption({ state, recordedDecision }: { state: RunState; recordedDecision: boolean }) {
  const caption = captionFor(state, recordedDecision);
  if (!caption) return null;
  return (
    <div className="flex shrink-0 items-baseline gap-3 rounded-card border border-accent-2 bg-bg px-4 py-2.5" role="status" aria-live="polite">
      <span className="shrink-0 text-sm font-semibold text-accent">Now: {caption.title}</span>
      <span className="text-sm text-text-muted">{caption.text}</span>
    </div>
  );
}
