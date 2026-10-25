import { AnimatePresence, motion } from "framer-motion";
import { formatValue } from "../../format";
import { agentLabel } from "../../state/agents";
import { useRoom } from "../../state/RoomContext";

/** Side drawer for the selected fact (and the tool call that produced it) or the selected clause. */
export function DetailDrawer() {
  const { state, selectedFactId, selectFact, selectedClause, selectClause, contractClauses, openTrace } = useRoom();
  const fact = selectedFactId ? state.facts[selectedFactId] : undefined;
  const call = fact ? state.tools[fact.tool_call_id] : undefined;
  const clause = selectedClause
    ? state.results.clauses[selectedClause] ?? contractClauses.find((c) => c.clause === selectedClause)
    : undefined;
  const open = Boolean(selectedFactId || selectedClause);

  const close = () => {
    selectFact(null);
    selectClause(null);
  };

  return (
    <AnimatePresence>
      {open ? (
        <motion.aside
          key="drawer"
          initial={{ x: 380, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          exit={{ x: 380, opacity: 0 }}
          transition={{ type: "tween", duration: 0.2 }}
          className="fixed top-24 right-4 z-40 flex max-h-[70vh] w-[360px] flex-col rounded-card border border-border bg-bg shadow-xl"
          aria-label={selectedFactId ? "Fact source" : "Contract clause"}
        >
          <div className="flex items-center justify-between border-b border-border px-4 py-3">
            <h2 className="text-sm">{selectedFactId ? `Fact ${selectedFactId}` : `Clause ${selectedClause}`}</h2>
            <button type="button" onClick={close} className="text-sm text-text-muted hover:text-accent" aria-label="Close">
              ✕
            </button>
          </div>
          <div className="overflow-y-auto px-4 py-3 text-sm">
            {selectedFactId ? (
              fact ? (
                <dl className="grid grid-cols-[90px_1fr] gap-x-3 gap-y-2">
                  <dt className="text-text-muted">Value</dt>
                  <dd className="font-bold text-accent">{formatValue(fact.value, fact.unit)}</dd>
                  <dt className="text-text-muted">Tool</dt>
                  <dd className="font-mono text-xs">{fact.tool}</dd>
                  <dt className="text-text-muted">Field</dt>
                  <dd className="font-mono text-xs break-all">{fact.path}</dd>
                  <dt className="text-text-muted">Tool call</dt>
                  <dd className="font-mono text-xs">
                    {fact.tool_call_id}
                    {call ? ` by ${agentLabel(call.agent)}` : ""}
                  </dd>
                  {call ? (
                    <>
                      <dt className="text-text-muted">Arguments</dt>
                      <dd className="font-mono text-xs break-all">
                        {Object.keys(call.args).length ? JSON.stringify(call.args) : "none (run context only)"}
                      </dd>
                    </>
                  ) : null}
                  <dd className="col-span-2 mt-2 rounded bg-accent-tint p-2 text-xs text-accent">
                    Computed by a deterministic engine, not by a language model.
                  </dd>
                  <dd className="col-span-2 flex justify-end">
                    <button
                      type="button"
                      onClick={() => openTrace(fact.tool_call_id)}
                      className="text-xs font-semibold text-accent underline"
                    >
                      Show this tool call in the trace
                    </button>
                  </dd>
                </dl>
              ) : (
                <p className="text-alert">This fact id does not exist in this run.</p>
              )
            ) : clause ? (
              <>
                <h3 className="mb-2 text-sm">{clause.title}</h3>
                <p className="leading-relaxed whitespace-pre-line">{clause.text}</p>
              </>
            ) : (
              <p className="text-text-muted">This clause is not in the contract.</p>
            )}
          </div>
        </motion.aside>
      ) : null}
    </AnimatePresence>
  );
}
