import { useEffect, useMemo, useState } from "react";
import { api, type Clause, type ProjectInfo } from "./api/client";
import type { AgentId } from "./api/events";
import { fetchHealth } from "./api/health";
import { ChangeSelector, type RunRequest } from "./components/change/ChangeSelector";
import { ErrorBoundary } from "./components/common/ErrorBoundary";
import { GuideDialog } from "./components/layout/GuideDialog";
import { Header, type BackendState, type RoomView } from "./components/layout/Header";
import { RoomLayout } from "./components/layout/RoomLayout";
import { STAGES, type StageId } from "./components/layout/stages";
import { RoomProvider, type RoomValue, type SelectionValue } from "./state/RoomContext";
import { useRun } from "./state/useRun";

const VIEW_KEY = "pvr-room-view";
const GUIDE_KEY = "pvr-guide-seen";

/** Per-viewer preferences in browser storage; the page works the same when storage is unavailable. */
function readStored(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStored(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // storage blocked: the preference lasts for this page only
  }
}

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
  const [traceOpen, setTraceOpen] = useState(false);
  const [traceFocus, setTraceFocus] = useState<string | null>(null);
  const [view, setView] = useState<RoomView>(() => (readStored(VIEW_KEY) === "details" ? "details" : "simple"));
  const [guideOpen, setGuideOpen] = useState(() => readStored(GUIDE_KEY) === null);

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
    setTraceOpen(false);
    setTraceFocus(null);
  };

  const backToSelector = () => {
    run.reset();
    clearSelections();
  };

  const startLive = async (request: RunRequest) => {
    const started = await api.startRun(request);
    clearSelections();
    run.watch({ kind: "live", runId: started.run_id });
  };

  /** Replays stop at the decision, so the viewer decides. A recording that never reached a decision (or a
   * backend that cannot bring it back) plays as recorded instead. */
  const startReplay = async (traceId: string) => {
    clearSelections();
    try {
      const held = await api.replayToDecision(traceId);
      run.watch({ kind: "replay", traceId: held.run_id, speed, decide: true });
    } catch {
      run.watch({ kind: "replay", traceId, speed });
    }
  };

  const changeView = (next: RoomView) => {
    setView(next);
    writeStored(VIEW_KEY, next);
  };

  const closeGuide = () => {
    setGuideOpen(false);
    writeStored(GUIDE_KEY, "1");
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
      decisionReplay: run.source?.kind === "replay" && Boolean(run.source.decide),
      speed,
      project,
      agentFilter,
      setAgentFilter,
      openTrace: (toolCallId) => {
        setTraceFocus(toolCallId ?? null);
        setTraceOpen(true);
      },
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
        replay={run.source?.kind === "replay" ? (run.source.decide ? "decide" : "replay") : null}
        speed={speed}
        view={view}
        onView={changeView}
        onGuide={() => setGuideOpen(true)}
        onSpeed={changeSpeed}
        onNewChange={inRoom ? backToSelector : null}
        onTrace={
          inRoom
            ? () => {
                setTraceFocus(null);
                setTraceOpen(!traceOpen);
              }
            : null
        }
      />
      {inRoom ? (
        <ErrorBoundary onReset={backToSelector}>
          <RoomProvider value={value} selection={selection}>
            <RoomLayout
              connectionError={run.connectionError}
              liveAvailable={liveAvailable}
              onRerun={startLive}
              view={view}
              trace={{
                open: traceOpen,
                focusToolCall: traceFocus,
                close: () => setTraceOpen(false),
                clearFocus: () => setTraceFocus(null),
              }}
            />
          </RoomProvider>
        </ErrorBoundary>
      ) : (
        <ChangeSelector liveAvailable={liveAvailable} onRun={startLive} onReplay={(id) => void startReplay(id)} />
      )}
      <GuideDialog open={guideOpen} onClose={closeGuide} />
    </div>
  );
}
