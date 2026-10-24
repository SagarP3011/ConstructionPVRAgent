import { useEffect, useState } from "react";
import { fetchHealth } from "../../api/health";
import { StageProgress } from "./StageProgress";

type BackendState = "checking" | "connected" | "unreachable";

const BACKEND_LABEL: Record<BackendState, string> = {
  checking: "Checking backend",
  connected: "Backend connected",
  unreachable: "Backend not reachable",
};

const BACKEND_DOT: Record<BackendState, string> = {
  checking: "bg-border",
  connected: "bg-accent-2",
  unreachable: "bg-alert",
};

/** App header: title, proof-of-concept notice, stage progress and backend status. */
export function Header() {
  const [backend, setBackend] = useState<BackendState>("checking");

  useEffect(() => {
    const controller = new AbortController();
    fetchHealth(controller.signal)
      .then((h) => setBackend(h.status === "ok" ? "connected" : "unreachable"))
      .catch((err: unknown) => {
        if (!(err instanceof DOMException && err.name === "AbortError")) setBackend("unreachable");
      });
    return () => controller.abort();
  }, []);

  return (
    <header className="flex items-center justify-between gap-6 border-b border-border bg-bg px-8 py-4">
      <div>
        <h1 className="text-xl">PVR Agent Room</h1>
        <p className="text-sm text-text-muted">Proof of concept by Sekuen, prepared for Aldar. Illustrative data.</p>
      </div>
      <StageProgress current={null} />
      <div className="flex items-center gap-2 text-xs text-text-muted" role="status">
        <span className={`h-2 w-2 rounded-full ${BACKEND_DOT[backend]}`} aria-hidden="true" />
        {BACKEND_LABEL[backend]}
      </div>
    </header>
  );
}
