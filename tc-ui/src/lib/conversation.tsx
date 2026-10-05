"use client";

import * as React from "react";
import type { TaskStatus } from "@/lib/api/orchestrator";

/**
 * Conversation model for the Command Center.
 *
 * The real backend has no `/converse` endpoint; a "conversation" is a task
 * created via `POST /v1/tasks { prompt }`, which runs the Brain→tool loop and
 * returns a TaskSummary (the TC response). This model holds the user's message,
 * the TC response (answer/error), and the associated task_id so the UI can
 * observe the task and its events.
 */

export interface Message {
  id: string;
  role: "user" | "tc";
  content: string;
  /** Present on the TC message when it maps to a task. */
  taskId?: string;
  status?: TaskStatus;
  /** Network/submission error (distinct from a task FAILED status). */
  error?: boolean;
  ts: number;
}

interface ConversationContextValue {
  messages: Message[];
  /** True while a submission is in flight (drives the Orb to "thinking"). */
  submitting: boolean;
  /** The task currently being observed (most recent TC message with a taskId). */
  activeTaskId: string | null;
  addMessage: (m: Omit<Message, "id" | "ts">) => string;
  updateMessage: (id: string, patch: Partial<Message>) => void;
  setSubmitting: (v: boolean) => void;
  clear: () => void;
}

const ConversationContext = React.createContext<ConversationContextValue | null>(null);

export function ConversationProvider({ children }: { children: React.ReactNode }) {
  const [messages, setMessages] = React.useState<Message[]>([]);
  const [submitting, setSubmitting] = React.useState(false);

  const addMessage = React.useCallback((m: Omit<Message, "id" | "ts">) => {
    const id = `m-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    const full: Message = { ...m, id, ts: Date.now() };
    setMessages((prev) => [...prev, full]);
    return id;
  }, []);

  const updateMessage = React.useCallback((id: string, patch: Partial<Message>) => {
    setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, ...patch } : m)));
  }, []);

  const clear = React.useCallback(() => setMessages([]), []);

  const activeTaskId = React.useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].taskId) return messages[i].taskId!;
    }
    return null;
  }, [messages]);

  const value: ConversationContextValue = {
    messages,
    submitting,
    activeTaskId,
    addMessage,
    updateMessage,
    setSubmitting,
    clear,
  };

  return <ConversationContext.Provider value={value}>{children}</ConversationContext.Provider>;
}

export function useConversation(): ConversationContextValue {
  const ctx = React.useContext(ConversationContext);
  if (!ctx) throw new Error("useConversation must be used within ConversationProvider");
  return ctx;
}
