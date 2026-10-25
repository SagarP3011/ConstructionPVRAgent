import { motion } from "framer-motion";
import { memo, useEffect, useState, type ReactNode } from "react";
import { INTENT_LABEL } from "../../format";
import { agentLabel, AGENTS } from "../../state/agents";
import type { MessageView } from "../../state/runStore";
import { AgentIcon } from "../common/AgentIcon";
import { ClaimChip, FactRef } from "../common/Chips";

const CHARS_PER_TICK = 6;
const TICK_MS = 16;

/** Reveal text quickly, a few characters per frame; `speed` scales it. Skippable by the caller. */
function useTyping(text: string, enabled: boolean, speed: number): [string, boolean, () => void] {
  const [shown, setShown] = useState(enabled ? 0 : text.length);
  useEffect(() => {
    if (shown >= text.length) return;
    const t = setTimeout(() => setShown((n) => Math.min(text.length, n + Math.ceil(CHARS_PER_TICK * speed))), TICK_MS);
    return () => clearTimeout(t);
  }, [shown, text.length, speed]);
  return [text.slice(0, shown), shown < text.length, () => setShown(text.length)];
}

/** Message text with [F-0012] citations as clickable fact references. */
function RichText({ text }: { text: string }) {
  const parts: ReactNode[] = [];
  const pattern = /\[\s*(F-\d{4,})\s*\]/g;
  let last = 0;
  for (const match of text.matchAll(pattern)) {
    const index = match.index ?? 0;
    parts.push(text.slice(last, index));
    parts.push(<FactRef key={`${index}`} factId={match[1] ?? ""} />);
    last = index + match[0].length;
  }
  parts.push(text.slice(last));
  return <>{parts}</>;
}

function VerificationMark({ message }: { message: MessageView }) {
  const status = message.verification.status;
  if (message.intent === "VERIFY" || message.intent === "ASK") return null;
  if (status === "pending") return <span className="text-[10px] text-text-muted">checking…</span>;
  if (status === "pass") {
    return (
      <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-accent" title="Every number checked against the facts">
        <AgentIcon agent="verifier" size={12} /> verified
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-alert">
      <AgentIcon agent="verifier" size={12} /> {message.unresolved ? "unresolved" : "failed check"}
    </span>
  );
}

interface MessageBubbleProps {
  message: MessageView;
  /** The struck-through original when this message corrects one. */
  original?: MessageView | null;
  typing: boolean;
  /** Typing speed multiplier (the header speed control). */
  speed: number;
}

/** One agent message: who to whom, intent, text with fact citations, claim chips, verification.
 * Memoised: a message re-renders only when it changes, not with every streamed event. */
export const MessageBubble = memo(function MessageBubble({ message, original, typing, speed }: MessageBubbleProps) {
  const info = AGENTS[message.from];
  const [text, isTyping, skip] = useTyping(message.content, typing, speed);
  const failedOriginal = original && original.verification.status === "fail";
  return (
    <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="flex gap-2">
      <div
        className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full"
        style={
          message.from === "verifier"
            ? { border: `1.5px solid ${info.colour}`, color: info.colour }
            : { background: info.colour, color: "white" }
        }
      >
        <AgentIcon agent={message.from} size={15} />
      </div>
      <div
        className={`min-w-0 flex-1 rounded-card border px-3 py-2 ${
          message.verification.status === "fail" && message.intent !== "VERIFY" ? "border-alert" : "border-border"
        } ${message.intent === "ASK" ? "bg-accent-tint" : "bg-bg"}`}
      >
        <div className="mb-1 flex flex-wrap items-center gap-x-2 text-[11px]">
          <span className="font-semibold" style={{ color: info.colour }}>
            {info.label}
          </span>
          <span className="text-text-muted">to {agentLabel(message.to)}</span>
          <span className="rounded-full bg-surface-2 px-1.5 py-px text-[10px] font-semibold text-text">
            {INTENT_LABEL[message.intent] ?? message.intent}
          </span>
          {message.stage === "debate" ? <span className="text-text-muted">round {message.round}</span> : null}
          {message.stance ? (
            <span className="rounded-full bg-accent-tint px-1.5 py-px text-[10px] font-semibold text-accent">
              prefers {message.stance}
            </span>
          ) : null}
          <span className="ml-auto">
            <VerificationMark message={message} />
          </span>
        </div>

        {original ? (
          <div className="mb-2 rounded bg-surface p-2 text-xs text-text-muted">
            <div className="mb-1 text-[10px] font-semibold text-alert">
              Replaced after a failed check{failedOriginal ? `: ${original.verification.issues.join("; ")}` : ""}
            </div>
            <p className="line-through">{original.content}</p>
          </div>
        ) : null}

        <p
          className="text-sm leading-relaxed whitespace-pre-line"
          onClick={isTyping ? skip : undefined}
          title={isTyping ? "Click to show the whole message" : undefined}
        >
          <RichText text={text} />
          {isTyping ? <span className="ml-0.5 inline-block h-3 w-1 animate-pulse bg-accent-2 align-middle" /> : null}
        </p>

        {!isTyping && message.claims.length ? (
          <div className="mt-2 flex flex-wrap gap-1">
            {message.claims.map((c, i) => (
              <ClaimChip key={`${c.fact_id}-${i}`} claim={c} />
            ))}
          </div>
        ) : null}

        {message.verification.status === "fail" && message.intent !== "VERIFY" ? (
          <ul className="mt-2 list-disc pl-4 text-[11px] break-words text-alert">
            {message.verification.issues.map((issue) => (
              <li key={issue}>{issue}</li>
            ))}
          </ul>
        ) : null}
      </div>
    </motion.div>
  );
});
