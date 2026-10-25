import { useCallback, useEffect, useRef, useState } from "react";
import { openStream, type StreamSource } from "../api/client";
import type { RunEvent } from "../api/events";
import { initialRunState, reduceEvents, type RunState } from "./runStore";

export type Connection = "idle" | "streaming" | "ended" | "error";

const FLUSH_MS = 40;

export interface RunHandle {
  state: RunState;
  source: StreamSource | null;
  connection: Connection;
  connectionError: string | null;
  /** Start watching a live run or a replay; clears the previous run. */
  watch: (source: StreamSource) => void;
  /** Replay only: continue from the last event at a new speed. */
  setSpeed: (speed: number) => void;
  /** Stop watching and clear the run. */
  reset: () => void;
}

/**
 * One code path for live runs and replays: open an SSE stream, buffer its events and fold them into
 * the run state in batches (a run sends a few thousand events, many in the same millisecond).
 */
export function useRun(): RunHandle {
  const [state, setState] = useState<RunState>(initialRunState);
  const [source, setSource] = useState<StreamSource | null>(null);
  const [connection, setConnection] = useState<Connection>("idle");
  const [connectionError, setConnectionError] = useState<string | null>(null);

  const buffer = useRef<RunEvent[]>([]);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const close = useRef<(() => void) | null>(null);
  const lastEventId = useRef<string | null>(null);
  const sourceRef = useRef<StreamSource | null>(null);

  const flush = useCallback(() => {
    timer.current = null;
    const batch = buffer.current;
    buffer.current = [];
    if (batch.length) setState((s) => reduceEvents(s, batch));
  }, []);

  const stop = useCallback(() => {
    close.current?.();
    close.current = null;
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
  }, []);

  const open = useCallback(
    (next: StreamSource, after: string | null) => {
      stop();
      setConnection("streaming");
      setConnectionError(null);
      close.current = openStream(next, after, {
        onEvent: (event) => {
          lastEventId.current = event.event_id;
          buffer.current.push(event);
          if (!timer.current) timer.current = setTimeout(flush, FLUSH_MS);
        },
        onEnd: () => {
          flush();
          setConnection("ended");
        },
        onError: (message) => {
          flush();
          setConnection("error");
          setConnectionError(message);
        },
      });
    },
    [flush, stop],
  );

  const watch = useCallback(
    (next: StreamSource) => {
      buffer.current = [];
      lastEventId.current = null;
      setState(initialRunState());
      sourceRef.current = next;
      setSource(next);
      open(next, null);
    },
    [open],
  );

  const setSpeed = useCallback(
    (speed: number) => {
      const current = sourceRef.current;
      if (current?.kind !== "replay" || current.speed === speed) return;
      const next = { ...current, speed };
      sourceRef.current = next;
      setSource(next);
      if (close.current) {
        flush();
        open(next, lastEventId.current);
      }
    },
    [flush, open],
  );

  const reset = useCallback(() => {
    stop();
    buffer.current = [];
    lastEventId.current = null;
    setState(initialRunState());
    sourceRef.current = null;
    setSource(null);
    setConnection("idle");
    setConnectionError(null);
  }, [stop]);

  useEffect(() => stop, [stop]);

  return { state, source, connection, connectionError, watch, setSpeed, reset };
}
