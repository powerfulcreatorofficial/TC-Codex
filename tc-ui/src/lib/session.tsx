"use client";

import * as React from "react";
import type { TaskSummary } from "./api/orchestrator";

/**
 * In-memory session store.
 *
 * The backend exposes NO list-tasks endpoint, and the owner token (required for
 * approvals) is returned ONCE on task creation in a response header. Therefore
 * the frontend can only manage tasks the user created in THIS browser session,
 * and their owner tokens are held in memory only.
 *
 * SECURITY: nothing here is persisted to localStorage or sessionStorage, and
 * nothing is logged. A page reload clears the session (by design) — the user
 * simply creates a new task. See ENGINEERING_TC_STATUS.md for the backend gap.
 */

export interface SessionTask {
  taskId: string;
  /** Owner token for approvals — in memory only, never persisted. */
  ownerToken: string;
  summary: TaskSummary;
  createdAt: number;
}

interface SessionState {
  /** Session tasks keyed by task id, in creation order (most recent first). */
  tasks: SessionTask[];
  /** The task currently focused in the Command Center, if any. */
  currentTaskId: string | null;
}

interface SessionContextValue extends SessionState {
  addTask: (summary: TaskSummary, ownerToken: string) => void;
  updateTask: (taskId: string, summary: TaskSummary) => void;
  setCurrentTask: (taskId: string | null) => void;
  ownerOf: (taskId: string) => string | null;
  getTask: (taskId: string) => SessionTask | undefined;
  awaitingApprovals: SessionTask[];
}

const SessionContext = React.createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [tasks, setTasks] = React.useState<SessionTask[]>([]);
  const [currentTaskId, setCurrentTaskId] = React.useState<string | null>(null);

  const addTask = React.useCallback((summary: TaskSummary, ownerToken: string) => {
    setTasks((prev) => {
      const without = prev.filter((t) => t.taskId !== summary.task_id);
      return [
        {
          taskId: summary.task_id,
          ownerToken,
          summary,
          createdAt: Date.now(),
        },
        ...without,
      ];
    });
    setCurrentTaskId(summary.task_id);
  }, []);

  const updateTask = React.useCallback((taskId: string, summary: TaskSummary) => {
    setTasks((prev) => prev.map((t) => (t.taskId === taskId ? { ...t, summary } : t)));
  }, []);

  const getTask = React.useCallback(
    (taskId: string) => tasks.find((t) => t.taskId === taskId),
    [tasks],
  );

  const ownerOf = React.useCallback(
    (taskId: string) => {
      const t = tasks.find((x) => x.taskId === taskId);
      return t ? t.ownerToken : null;
    },
    [tasks],
  );

  const awaitingApprovals = React.useMemo(
    () => tasks.filter((t) => t.summary.status === "AWAITING_APPROVAL"),
    [tasks],
  );

  const value: SessionContextValue = {
    tasks,
    currentTaskId,
    addTask,
    updateTask,
    setCurrentTask: setCurrentTaskId,
    ownerOf,
    getTask,
    awaitingApprovals,
  };

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const ctx = React.useContext(SessionContext);
  if (!ctx) throw new Error("useSession must be used within SessionProvider");
  return ctx;
}
