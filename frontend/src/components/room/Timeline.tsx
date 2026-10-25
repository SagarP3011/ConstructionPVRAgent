import { useEffect, useRef, useState } from "react";
import { AGENTS } from "../../state/agents";
import { visibleTimeline } from "../../state/runStore";
import { useRoom } from "../../state/RoomContext";
import { STAGES } from "../layout/stages";
import { EmptyState } from "../layout/Panel";
import { MessageBubble } from "./MessageBubble";
import { ToolCallRow } from "./ToolCallRow";

const STAGE_LABEL: Record<string, string> = Object.fromEntries(STAGES.map((s) => [s.id, s.label]));

/** Chat-style timeline of messages and tool calls. Follows the newest item unless the viewer scrolls up. */
export function Timeline() {
  const { state, agentFilter, setAgentFilter, speed, selectedFactId } = useRoom();
  const highlightedCall = selectedFactId ? state.facts[selectedFactId]?.tool_call_id ?? null : null;
  const items = visibleTimeline(state, agentFilter);
  const scroller = useRef<HTMLDivElement>(null);
  const [follow, setFollow] = useState(true);
  // Messages already present when the timeline first rendered do not type out again.
  const seenAtMount = useRef<Set<string> | null>(null);
  if (seenAtMount.current === null) seenAtMount.current = new Set(Object.keys(state.messages));

  useEffect(() => {
    if (state.seq === 0) seenAtMount.current = new Set();
  }, [state.seq]);

  // Stay at the newest item while following, also as a message types out and grows.
  const content = useRef<HTMLDivElement>(null);
  const followRef = useRef(follow);
  followRef.current = follow;
  useEffect(() => {
    const el = scroller.current;
    if (el && follow) el.scrollTop = el.scrollHeight;
  }, [items.length, follow]);
  useEffect(() => {
    const el = scroller.current;
    const inner = content.current;
    if (!el || !inner || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => {
      if (followRef.current) el.scrollTop = el.scrollHeight;
    });
    observer.observe(inner);
    return () => observer.disconnect();
  }, []);

  const onScroll = () => {
    const el = scroller.current;
    if (el) setFollow(el.scrollHeight - el.scrollTop - el.clientHeight < 60);
  };

  const filtered = agentFilter ? state.agents[agentFilter] : null;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {filtered && agentFilter ? (
        <div className="flex flex-wrap items-center gap-2 border-b border-border bg-accent-tint px-4 py-2 text-xs">
          <span>
            Showing <strong style={{ color: AGENTS[agentFilter].colour }}>{AGENTS[agentFilter].label}</strong> only.
          </span>
          {filtered.stanceHistory.length ? (
            <span className="text-text-muted">
              Stance:{" "}
              {filtered.stanceHistory.map((h, i) => (
                <span key={`${h.messageId}-${i}`}>
                  {i > 0 ? " → " : ""}
                  <strong className="text-accent">{h.to}</strong> ({h.when.replace("_", " ")})
                </span>
              ))}
            </span>
          ) : null}
          <button type="button" onClick={() => setAgentFilter(null)} className="ml-auto font-semibold text-accent">
            Show everyone
          </button>
        </div>
      ) : null}
      <div ref={scroller} onScroll={onScroll} className="flex min-h-0 flex-1 flex-col overflow-x-hidden overflow-y-auto p-4">
        <div ref={content} className="flex flex-col gap-2">
        {items.length === 0 ? <EmptyState message="Agent messages and tool calls appear here." /> : null}
        {items.map((item) => {
          if (item.kind === "stage") {
            return (
              <div key={`stage-${item.seq}`} className="my-1 flex items-center gap-2 text-[11px] font-semibold text-accent">
                <span className="h-px flex-1 bg-border" />
                {STAGE_LABEL[item.stage] ?? item.stage}
                <span className="h-px flex-1 bg-border" />
              </div>
            );
          }
          if (item.kind === "tool") {
            const call = state.tools[item.id];
            return call ? <ToolCallRow key={item.id} call={call} highlighted={call.id === highlightedCall} /> : null;
          }
          const m = state.messages[item.id];
          if (!m) return null;
          const replacement = m.superseded_by ? state.messages[m.superseded_by] : undefined;
          const shown = replacement ?? m;
          return (
            <MessageBubble
              key={shown.message_id}
              message={shown}
              original={replacement ? m : null}
              typing={!seenAtMount.current?.has(shown.message_id)}
              speed={speed}
            />
          );
        })}
        </div>
      </div>
      {!follow ? (
        <button
          type="button"
          onClick={() => setFollow(true)}
          className="mx-auto -mt-10 mb-2 rounded-full bg-accent px-3 py-1 text-xs text-white shadow"
        >
          Jump to latest
        </button>
      ) : null}
    </div>
  );
}
