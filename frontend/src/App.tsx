import { useEffect, useMemo, useState } from "react";
import { api, type Clause, type ProjectInfo } from "./api/client";
import type { AgentId } from "./api/events";
import { fetchHealth } from "./api/health";
import { ChangeSelector, type RunRequest } from "./components/change/ChangeSelector";
import { Header, type BackendState } from "./components/layout/Header";
import { RoomLayout } from "./components/layout/RoomLayout";
import { STAGES, type StageId } from "./components/layout/stages";
import { RoomProvider, type RoomValue, type SelectionValue } from "./state/RoomContext";
import { useRun } from "./state/useRun";

function asStage(stage: string | null): StageId | null {
  return STAGES.some((s) => s.id === stage) ? (stage as StageId) : null;
}

export default function App() {
  const run = useRun();
  const [backend, setBackend] = useState<BackendState>("checking");
  const [liveAvailable, setLiveAvailable] = useState<boolean | null>(null);
  const [project, setProject] = useState<ProjectInfo | null>(null);
  const [clauses, setClauses] = useState<Clause[]>([]);
  const [speed, setSpeed] = useState(1);
  const [selectedFactId, selectFact] = useState<string | null>(null);
  const [selectedClause, selectClause] = useState<string | null>(null);
  const [agentFilter, setAgentFilter] = useState<AgentId | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetchHealth(controller.signal)
      .then((h) => {
        setBackend(h.status === "ok" ? "connected" : "unreachable");
        setLiveAvailable(h.live_runs_available ?? null);
        api.project().then(setProject).catch(() => setProject(null));
        api.contract().then((c) => setClauses(c.clauses)).catch(() => setClauses([]));
      })
      .catch((err: unknown) => {
        if (!(err instanceof DOMException && err.name === "AbortError")) setBackend("unreachable");
      });
    return () => controller.abort();
  }, []);

  const clearSelections = () => {
    selectFact(null);
    selectClause(null);
    setAgentFilter(null);
  };

  const startLive = async (request: RunRequest) => {
    const started = await api.startRun(request);
    clearSelections();
    run.watch({ kind: "live", runId: started.run_id });
  };

  const startReplay = (traceId: string) => {
    clearSelections();
    run.watch({ kind: "replay", traceId, speed });
  };

  const changeSpeed = (next: number) => {
    setSpeed(next);
    run.setSpeed(next);
  };

  const inRoom = run.source !== null;
  const selection: SelectionValue = useMemo(
    () => ({
      contractClauses: clauses,
      selectedFactId,
      selectFact: (id) => {
        selectClause(null);
        selectFact(id);
      },
      selectedClause,
      selectClause: (id) => {
        selectFact(null);
        selectClause(id);
      },
    }),
    [clauses, selectedFactId, selectedClause],
  );
  const value: RoomValue = useMemo(
    () => ({
      ...selection,
      state: run.state,
      isReplay: run.source?.kind === "replay",
      speed,
      project,
      agentFilter,
      setAgentFilter,
    }),
    [selection, run.state, run.source, speed, project, agentFilter],
  );

  return (
    <div className="flex h-full min-w-[1280px] flex-col">
      <Header
        backend={backend}
        context={inRoom ? run.state.context : null}
        stage={inRoom ? asStage(run.state.stage) : null}
        stagesDone={inRoom ? run.state.stagesDone : []}
        replay={run.source?.kind === "replay"}
        speed={speed}
        onSpeed={changeSpeed}
        onNewChange={
          inRoom
            ? () => {
                run.reset();
                clearSelections();
              }
            : null
        }
      />
      {inRoom ? (
        <RoomProvider value={value} selection={selection}>
          <RoomLayout connectionError={run.connectionError} />
        </RoomProvider>
      ) : (
        <ChangeSelector liveAvailable={liveAvailable} onRun={startLive} onReplay={startReplay} />
      )}
    </div>
  );
}
