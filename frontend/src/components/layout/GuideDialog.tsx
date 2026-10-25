import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";

interface Step {
  title: string;
  body: string[];
}

export const GUIDE_STEPS: Step[] = [
  {
    title: "What this is",
    body: [
      "A contractor asks to change the works, for example to raise a boundary wall. Someone has to work out what it costs, how long it adds, what the contract allows and what to do about it.",
      "Here a team of seven AI agents does that groundwork together, the way a project team would, and prepares the decision for a person.",
    ],
  },
  {
    title: "The Agent Room",
    body: [
      "Each circle is an agent with one job: Intake, Contract, Cost, Time, Commercial, a Moderator and a Verifier. A circle lights up while that agent works.",
      "Lines show who is talking to whom. The Timeline next to it lists every message and tool call as it happens.",
    ],
  },
  {
    title: "Where the numbers come from",
    body: [
      "The AI never makes up a number. Every figure comes from calculation code (the engines) through a tool, and gets a fact id such as F-0012.",
      "The Verifier checks each message against those facts. A message that fails is sent back to be corrected. Click any fact to see where it came from.",
    ],
  },
  {
    title: "The debate and the options",
    body: [
      "The agents argue for the option they prefer, for example paying for an extra crew or accepting a delay. At the end you get the options worth choosing between, each with its cost, delay and the effect on the buffer and contingency.",
    ],
  },
  {
    title: "Your decision",
    body: [
      "Nothing happens until a named person picks an option and approves it. Only then are the PVR form, the verification report, the tasks and the notifications written.",
      "Saved runs replay at no cost and stop at this point too, so you take the decision yourself.",
    ],
  },
  {
    title: "Simple view and details",
    body: [
      "The simple view shows the agents, what is happening now and the decision. Show details adds the evidence, the cost, schedule, buffer and options tabs, and what-if controls.",
      "Trace in the header lists every event of the run. Open this guide again with the ? button.",
    ],
  },
];

interface GuideDialogProps {
  open: boolean;
  onClose: () => void;
}

/** "What am I looking at?": a short walkthrough of the screen, shown on first visit and from the ? button. */
export function GuideDialog({ open, onClose }: GuideDialogProps) {
  const [index, setIndex] = useState(0);
  const step = GUIDE_STEPS[index] ?? GUIDE_STEPS[0]!;
  const last = index === GUIDE_STEPS.length - 1;
  const close = () => {
    setIndex(0);
    onClose();
  };

  return (
    <AnimatePresence>
      {open ? (
        <motion.div
          key="guide"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/30"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={close}
        >
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-label="What am I looking at?"
            className="w-[520px] rounded-card bg-bg p-6 shadow-2xl"
            initial={{ scale: 0.95, y: 10 }}
            animate={{ scale: 1, y: 0 }}
            onClick={(e) => e.stopPropagation()}
          >
            <p className="mb-1 text-xs text-text-muted">
              What am I looking at? · {index + 1} of {GUIDE_STEPS.length}
            </p>
            <h2 className="mb-3 text-lg">{step.title}</h2>
            <div className="mb-5 flex min-h-[132px] flex-col gap-2 text-sm">
              {step.body.map((p) => (
                <p key={p}>{p}</p>
              ))}
            </div>
            <div className="flex items-center justify-between">
              <div className="flex gap-1.5" aria-hidden="true">
                {GUIDE_STEPS.map((s, i) => (
                  <span key={s.title} className={`h-1.5 w-5 rounded-full ${i === index ? "bg-accent" : "bg-border"}`} />
                ))}
              </div>
              <div className="flex gap-2">
                <button type="button" onClick={close} className="rounded-full px-4 py-2 text-sm text-text-muted hover:text-accent">
                  {last ? "Close" : "Skip"}
                </button>
                {index > 0 ? (
                  <button
                    type="button"
                    onClick={() => setIndex(index - 1)}
                    className="rounded-full border border-accent px-4 py-2 text-sm font-semibold text-accent"
                  >
                    Back
                  </button>
                ) : null}
                <button
                  type="button"
                  onClick={() => (last ? close() : setIndex(index + 1))}
                  className="rounded-full bg-accent px-5 py-2 text-sm font-semibold text-white"
                >
                  {last ? "Got it" : "Next"}
                </button>
              </div>
            </div>
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
