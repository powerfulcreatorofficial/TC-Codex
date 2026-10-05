"use client";

import * as React from "react";
import { Check, Copy, RotateCcw } from "lucide-react";
import { cn } from "@/lib/cn";
import { TCOrb, type OrbState } from "@/components/signature/TCOrb";
import type { Message } from "@/lib/conversation";
import type { TaskStatus } from "@/lib/api/orchestrator";

const statusLabel: Record<TaskStatus, string> = {
  PENDING: "Queued",
  RUNNING: "Working",
  AWAITING_APPROVAL: "Awaiting approval",
  COMPLETED: "Verified",
  FAILED: "Failed",
};

function MessageBubble({ m }: { m: Message }) {
  const [copied, setCopied] = React.useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(m.content);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1200);
    } catch {
      setCopied(false);
    }
  };

  if (m.role === "user") {
    return (
      <div className="group flex justify-end">
        <div className="max-w-[88%] sm:max-w-[78%]">
          <div className="rounded-2xl rounded-br-md bg-tc px-4 py-3 text-sm leading-6 text-white shadow-sm">
            {m.content}
          </div>
          <div className="mt-1 flex justify-end text-[10px] text-text-muted opacity-0 transition group-hover:opacity-100">
            <button type="button" onClick={copy} className="inline-flex items-center gap-1 hover:text-text" aria-label="Copy message">
              {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />} copy
            </button>
          </div>
        </div>
      </div>
    );
  }

  const isErr = m.error || m.status === "FAILED";
  return (
    <div className="group flex items-start gap-3">
      <div className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-xl border border-tc/15 bg-soft-green">
        <TCOrb state={isErr ? "error" : m.status === "COMPLETED" ? "success" : "idle"} size={23} />
      </div>
      <div className="min-w-0 max-w-[90%] flex-1 sm:max-w-[82%]">
        <div
          className={cn(
            "rounded-2xl rounded-bl-md border px-4 py-3 shadow-xs",
            isErr ? "border-error/20 bg-error/5" : "border-border bg-surface",
          )}
        >
          <div className="whitespace-pre-wrap break-words text-sm leading-6 text-text">{m.content}</div>
          <div className="mt-3 flex flex-wrap items-center gap-2 text-[10px] text-text-muted">
            {m.taskId ? <span className="rounded-pill bg-surface-2 px-2 py-1 font-mono">task · {m.taskId.slice(0, 12)}</span> : null}
            {m.status && !isErr ? <span>{statusLabel[m.status]}</span> : null}
            {m.taskId && m.status === "FAILED" ? (
              <button type="button" disabled title="Use the task detail page to retry this run" className="inline-flex items-center gap-1 rounded-pill border border-border px-2 py-1 opacity-60">
                <RotateCcw className="h-3 w-3" /> retry from task
              </button>
            ) : null}
            <button type="button" onClick={copy} className="ml-auto inline-flex items-center gap-1 rounded-pill border border-border bg-surface px-2 py-1 opacity-0 transition group-hover:opacity-100 hover:text-text" aria-label="Copy response">
              {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export function ConversationView({ messages, orbState }: { messages: Message[]; orbState: OrbState }) {
  const endRef = React.useRef<HTMLDivElement>(null);
  const containerRef = React.useRef<HTMLDivElement>(null);
  const [stick, setStick] = React.useState(true);

  React.useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const onScroll = () => setStick(el.scrollHeight - el.scrollTop - el.clientHeight < 100);
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, []);

  React.useEffect(() => {
    if (stick) endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, stick]);

  if (messages.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-border bg-surface/50 px-5 py-10 text-center">
        <TCOrb state={orbState} size={68} />
        <p className="mt-4 text-sm font-medium text-text">TC is ready for an engineering request.</p>
        <p className="mt-1 text-xs text-text-muted">Start small or give TC a complete project objective.</p>
      </div>
    );
  }

  return (
    <div ref={containerRef} className="max-h-[min(62vh,620px)] space-y-5 overflow-y-auto px-1 pb-2 scrollbar-thin">
      {messages.map((m) => <MessageBubble key={m.id} m={m} />)}
      <div ref={endRef} />
    </div>
  );
}
