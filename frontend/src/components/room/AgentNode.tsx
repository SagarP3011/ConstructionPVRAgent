import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useState } from "react";
import type { AgentId } from "../../api/events";
import { AGENTS } from "../../state/agents";
import type { AgentView } from "../../state/runStore";
import { AgentIcon } from "../common/AgentIcon";

export type AgentNodeData = {
  agent: AgentId;
  view: AgentView;
  selected: boolean;
  dimmed: boolean;
  showStance: boolean;
};

export type AgentNodeType = Node<AgentNodeData, "agent">;

const SPARK_MS = 1600;

const HANDLE_STYLE = { left: "50%", top: "50%", opacity: 0, width: 1, height: 1, border: 0 } as const;

/** One agent in the room: icon, label, pulse while working, tool sparks and the current stance. */
export function AgentNode({ data }: NodeProps<AgentNodeType>) {
  const info = AGENTS[data.agent];
  const { view } = data;
  const [spark, setSpark] = useState<string | null>(null);

  useEffect(() => {
    if (!view.lastTool) return;
    setSpark(view.lastTool.tool);
    const t = setTimeout(() => setSpark(null), SPARK_MS);
    return () => clearTimeout(t);
  }, [view.lastTool]);

  const verifier = data.agent === "verifier";
  return (
    <div
      className={`relative flex w-[112px] cursor-pointer flex-col items-center gap-1 transition-opacity ${
        data.dimmed ? "opacity-35" : ""
      }`}
      title={`${info.label}: ${info.role}`}
    >
      <Handle type="target" position={Position.Top} style={HANDLE_STYLE} isConnectable={false} />
      <Handle type="source" position={Position.Top} style={HANDLE_STYLE} isConnectable={false} />

      <div className="relative">
        {view.active ? (
          <motion.span
            className="absolute inset-0 rounded-full"
            style={{ border: `2px solid ${info.colour}` }}
            initial={{ scale: 1, opacity: 0.8 }}
            animate={{ scale: 1.55, opacity: 0 }}
            transition={{ duration: 1.3, repeat: Infinity, ease: "easeOut" }}
            aria-hidden="true"
          />
        ) : null}
        <div
          className="relative flex h-12 w-12 items-center justify-center rounded-full"
          style={
            verifier
              ? { border: `2px solid ${info.colour}`, color: info.colour, background: "var(--bg)" }
              : { background: info.colour, color: "white" }
          }
        >
          <AgentIcon agent={data.agent} size={24} />
        </div>
        <AnimatePresence>
          {spark ? (
            <motion.span
              key={`${spark}-${view.lastTool?.seq ?? 0}`}
              initial={{ opacity: 0, y: 4, scale: 0.8 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -6 }}
              className="absolute -top-5 left-1/2 -translate-x-1/2 rounded-full bg-accent-2 px-1.5 py-0.5 font-mono text-[9px] whitespace-nowrap text-white shadow"
            >
              ⚡ {spark}
            </motion.span>
          ) : null}
        </AnimatePresence>
      </div>

      <span
        className={`text-xs font-semibold ${data.selected ? "underline underline-offset-2" : ""}`}
        style={{ color: info.colour }}
      >
        {info.label}
      </span>
      {data.showStance ? (
        <AnimatePresence mode="wait">
          <motion.span
            key={view.stance ?? "none"}
            initial={{ opacity: 0, scale: 0.7 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.7 }}
            className={`rounded-full px-2 py-0.5 text-[10px] font-semibold whitespace-nowrap ${
              view.stance ? "bg-accent-tint text-accent" : "bg-surface-2 text-text-muted"
            }`}
          >
            {view.stance ?? "no stance yet"}
          </motion.span>
        </AnimatePresence>
      ) : null}
    </div>
  );
}
