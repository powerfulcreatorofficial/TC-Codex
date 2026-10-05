"use client";

import * as React from "react";
import {
  orchestrator,
  type HealthResponse,
  type TaskSummary,
  type TaskEvent,
  type Learning,
  OrchestratorApiError,
} from "@/lib/api/orchestrator";

/** Terminal task statuses — polling stops once reached. */
export function isTerminal(status: TaskSummary["status"] | undefined): boolean {
  return status === "COMPLETED" || status === "FAILED";
}

export type ConnectionState = "connected" | "connecting" | "disconnected" | "unknown";

export function useTasks(limit = 100) {
  const [tasks, setTasks] = React.useState<TaskSummary[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  const refresh = React.useCallback(async () => {
    try {
      setError(null);
      const next = await orchestrator.listTasks({ limit });
      setTasks(next);
    } catch (e) {
      setError(e instanceof OrchestratorApiError ? e.message : "failed to load tasks");
    } finally {
      setLoading(false);
    }
  }, [limit]);

  React.useEffect(() => {
    void refresh();
  }, [refresh]);

  return { tasks, loading, error, refresh };
}


/** Polls /health at a low frequency to drive the connection indicator. */
export function useHealth(intervalMs = 10000) {
  const [health, setHealth] = React.useState<HealthResponse | null>(null);
  const [state, setState] = React.useState<ConnectionState>("connecting");
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;

    const tick = async () => {
      try {
        setState((s) => (s === "disconnected" ? "connecting" : s));
        const h = await orchestrator.health();
        if (!active) return;
        setHealth(h);
        setState("connected");
        setError(null);
      } catch (e) {
        if (!active) return;
        setState("disconnected");
        setError(e instanceof OrchestratorApiError ? e.message : "unreachable");
      } finally {
        if (active) timer = setTimeout(tick, intervalMs);
      }
    };
    tick();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [intervalMs]);

  return { health, state, error };
}

/**
 * Polls a task's status. Polls only while non-terminal; stops on terminal.
 * `enabled` allows a parent to pause polling (e.g. when the detail view is
 * not mounted).
 */
export function useTask(taskId: string | null | undefined, enabled = true) {
  const [summary, setSummary] = React.useState<TaskSummary | null>(null);
  const [loading, setLoading] = React.useState<boolean>(!!taskId && enabled);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!taskId || !enabled) {
      setLoading(false);
      return;
    }
    let active = true;
    let timer: ReturnType<typeof setTimeout>;

    const tick = async () => {
      try {
        const s = await orchestrator.getTask(taskId);
        if (!active) return;
        setSummary(s);
        setError(null);
        setLoading(false);
        if (isTerminal(s.status)) return; // stop polling
        timer = setTimeout(tick, 2500);
      } catch (e) {
        if (!active) return;
        setError(e instanceof OrchestratorApiError ? e.message : "failed to load task");
        setLoading(false);
      }
    };
    tick();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [taskId, enabled]);

  return { summary, loading, error };
}

/** Polling event stream. Polls while the task is active; stops on terminal.
 *
 * Status follows the Phase 5.3 connection model: connecting → live →
 * reconnecting → disconnected. Polling ~1.5s while active; stops on terminal.
 */
export type EventStreamStatus = "connecting" | "live" | "reconnecting" | "disconnected" | "done";

export function useEventStream(taskId: string | null | undefined, enabled = true) {
  const [events, setEvents] = React.useState<TaskEvent[]>([]);
  const [lastUpdated, setLastUpdated] = React.useState<number | null>(null);
  const [status, setStatus] = React.useState<EventStreamStatus>("connecting");
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!taskId || !enabled) {
      setStatus("connecting");
      return;
    }

    let active = true;
    let source: EventSource | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | undefined;
    let fallbackTimer: ReturnType<typeof setTimeout> | undefined;
    const seen = new Set<number>();

    const apply = (event: TaskEvent) => {
      if (!active || seen.has(event.id)) return;
      seen.add(event.id);
      setEvents((prev) => [...prev, event].sort((a, b) => a.id - b.id));
      setLastUpdated(Date.now());
      setError(null);
      setStatus(
        event.event_type === "task_completed" || event.event_type === "task_failed"
          ? "done"
          : "live",
      );
    };

    const hydrate = async () => {
      try {
        const initial = await orchestrator.listEvents(taskId);
        if (!active) return false;
        initial.forEach(apply);
        return initial.some(
          (event) => event.event_type === "task_completed" || event.event_type === "task_failed",
        );
      } catch (e) {
        if (!active) return true;
        setError(e instanceof OrchestratorApiError ? e.message : "failed to load events");
        return false;
      }
    };

    const connect = async () => {
      const terminal = await hydrate();
      if (!active || terminal) return;

      setStatus("live");
      source = new EventSource(orchestrator.eventsStreamUrl(taskId));
      source.onmessage = (message) => {
        try {
          apply(JSON.parse(message.data) as TaskEvent);
        } catch {
          setError("received an invalid event from TC");
        }
      };
      source.onerror = () => {
        if (!active) return;
        source?.close();
        source = null;
        setStatus("reconnecting");
        if (!reconnectTimer) {
          reconnectTimer = setTimeout(() => {
            reconnectTimer = undefined;
            void connect();
          }, 2500);
        }
      };
    };

    fallbackTimer = setInterval(async () => {
      if (!active) return;
      try {
        const latest = await orchestrator.listEvents(taskId);
        latest.forEach(apply);
      } catch {
        // SSE remains the primary channel; REST fallback is best effort.
      }
    }, 5000);

    void connect();
    return () => {
      active = false;
      source?.close();
      source = null;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (fallbackTimer) clearInterval(fallbackTimer);
    };
  }, [taskId, enabled]);

  return { events, lastUpdated, status, error };
}


export function useLearnings(limit = 8) {
  const [learnings, setLearnings] = React.useState<Learning[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  const refresh = React.useCallback(async () => {
    try {
      setError(null);
      setLearnings(await orchestrator.listLearnings(limit));
    } catch (e) {
      setError(e instanceof OrchestratorApiError ? e.message : "failed to load TC memory");
    } finally {
      setLoading(false);
    }
  }, [limit]);

  React.useEffect(() => {
    void refresh();
  }, [refresh]);

  return { learnings, loading, error, refresh };
}
