import { memo, useEffect, useRef, useState } from "react";
import { AGENTS, isAgentId } from "../../state/agents";
import type { ToolCallView } from "../../state/runStore";
import { toolArgs, toolSummary } from "./toolSummary";

/** A collapsible row: "Time called run_cpm (with the change): completion day 95". */
export const ToolCallRow = memo(function ToolCallRow({ call, highlighted = false }: { call: ToolCallView; highlighted?: boolean }) {
  const [open, setOpen] = useState(false);
  const row = useRef<HTMLDivElement>(null);
  // The tool call behind the fact the viewer selected: open it and bring it into view.
  useEffect(() => {
    if (!highlighted) return;
    setOpen(true);
    row.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [highlighted]);
  const agent = isAgentId(call.agent) ? AGENTS[call.agent] : null;
  const args = toolArgs(call);
  return (
    <div ref={row} className={`pl-9 text-[11px] ${highlighted ? "rounded bg-accent-tint ring-2 ring-accent-2" : ""}`}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className={`flex w-full items-start gap-1.5 rounded px-2 py-1 text-left hover:bg-surface ${
          call.ok === false ? "text-alert" : "text-text-muted"
        }`}
        aria-expanded={open}
      >
        <span aria-hidden="true">{open ? "▾" : "▸"}</span>
        <span>
          <span className="font-semibold" style={agent ? { color: agent.colour } : undefined}>
            {agent?.label ?? call.agent}
          </span>{" "}
          called <span className="font-mono">{call.tool}</span>
          {args ? <span> ({args})</span> : null}: {toolSummary(call)}
        </span>
      </button>
      {open ? (
        <div className="mt-1 mb-2 ml-6 rounded bg-surface p-2 font-mono text-[10px] text-text-muted">
          <div>
            {call.id} · arguments {JSON.stringify(call.args)}
          </div>
          {call.factIds.length ? (
            <div className="mt-1 break-all">
              facts {call.factIds.slice(0, 12).join(", ")}
              {call.factIds.length > 12 ? ` and ${call.factIds.length - 12} more` : ""}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
});
