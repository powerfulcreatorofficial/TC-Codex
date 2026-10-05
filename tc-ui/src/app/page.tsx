"use client";

import * as React from "react";
import Link from "next/link";
import {
  ArrowRight,
  CheckCircle2,
  ChevronRight,
  CircleDot,
  GitBranch,
  ShieldCheck,
  Sparkles,
  TerminalSquare,
  WandSparkles,
} from "lucide-react";
import { AppShell } from "@/components/shell/AppShell";
import { Composer } from "@/components/Composer";
import { ConversationView } from "@/components/ConversationView";
import { TCOrb } from "@/components/signature/TCOrb";
import { ActivityTimeline } from "@/components/signature/ActivityTimeline";
import { MemoryPanel } from "@/components/MemoryPanel";
import { Card, CardBody, Badge, Button } from "@/components/primitives";
import { orchestrator, OrchestratorApiError, type TaskStatus } from "@/lib/api/orchestrator";
import { useSession } from "@/lib/session";
import { ConversationProvider, useConversation } from "@/lib/conversation";
import { useEventStream, useHealth, useTask, useTasks } from "@/lib/hooks/use-api";
import { statusToOrb, eventToActivity } from "@/lib/event-mapping";

function calmError(e: unknown, connectionDown: boolean): string {
  if (connectionDown) return "The orchestrator is unreachable. TC will be ready when the control plane reconnects.";
  if (e instanceof OrchestratorApiError) {
    if (e.status === 401 || e.status === 403) return "TC rejected the request authorization. Check the current session.";
    if (e.status >= 500) return "TC's control plane returned an error. Retry the task in a moment.";
    return "TC couldn't accept that engineering request. Please try again.";
  }
  return "The request could not reach TC. Check the local connection and retry.";
}

const starterPrompts = [
  { icon: WandSparkles, title: "Build a feature", text: "Build a small feature in my project and verify it with tests." },
  { icon: TerminalSquare, title: "Debug a failure", text: "Inspect the current project, find the failing test, and repair it." },
  { icon: GitBranch, title: "Review my repo", text: "Inspect the repository and summarize the highest-impact engineering issues." },
];

const statusStyles: Record<TaskStatus, string> = {
  PENDING: "text-text-muted",
  RUNNING: "text-emerald",
  AWAITING_APPROVAL: "text-warning",
  COMPLETED: "text-success",
  FAILED: "text-error",
};

function Stat({ label, value, detail, tone = "default" }: { label: string; value: string; detail: string; tone?: "default" | "accent" | "success" }) {
  return (
    <div className="rounded-2xl border border-border bg-surface/70 px-4 py-4 shadow-xs">
      <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-text-muted">{label}</p>
      <div className="mt-2 flex items-end justify-between gap-3">
        <p className={tone === "success" ? "text-2xl font-semibold tracking-tight text-success" : tone === "accent" ? "text-2xl font-semibold tracking-tight text-emerald" : "text-2xl font-semibold tracking-tight text-text"}>{value}</p>
        <p className="text-right font-mono text-[10px] text-text-muted">{detail}</p>
      </div>
    </div>
  );
}

function CurrentTaskPanel({ taskId }: { taskId: string }) {
  const { summary } = useTask(taskId);
  const { events, status: streamStatus } = useEventStream(taskId, true);
  const eventCount = events.length;
  const status = summary?.status ?? "RUNNING";
  const completedSteps = Math.max(0, summary?.current_step ?? 0);
  const maxSteps = Math.max(1, summary?.max_steps ?? 20);
  const progress = Math.min(100, Math.round((completedSteps / maxSteps) * 100));

  return (
    <Card className="overflow-hidden">
      <div className="border-b border-border bg-surface-2/50 px-4 py-3.5 sm:px-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <span className="grid h-8 w-8 place-items-center rounded-lg bg-soft-green">
              <CircleDot className="h-4 w-4 text-emerald" />
            </span>
            <div>
              <p className="text-sm font-semibold text-text">Live engineering run</p>
              <p className="font-mono text-[10px] text-text-muted">{taskId.slice(0, 16)}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className={statusStyles[status]}>{status.replaceAll("_", " ")}</span>
            <span className="font-mono text-[10px] text-text-muted">stream · {streamStatus}</span>
          </div>
        </div>
      </div>
      <CardBody className="space-y-4">
        <div>
          <div className="flex items-start justify-between gap-4">
            <p className="max-w-3xl text-sm leading-6 text-text">{summary?.prompt ?? "TC is loading the active engineering task…"}</p>
            <Link href={`/tasks/${taskId}`} className="hidden shrink-0 sm:block">
              <Button variant="ghost" size="sm">Open <ArrowRight className="h-3.5 w-3.5" /></Button>
            </Link>
          </div>
          <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-surface-2">
            <div className="h-full rounded-full bg-tc transition-[width] duration-base ease-smooth" style={{ width: `${progress}%` }} />
          </div>
          <div className="mt-2 flex justify-between font-mono text-[10px] text-text-muted">
            <span>{completedSteps}/{maxSteps} agent steps</span>
            <span>{eventCount} recorded events</span>
          </div>
        </div>
        <div className="grid gap-2 sm:grid-cols-3">
          {[
            ["Planner", status === "PENDING" ? "starting" : "active"],
            ["Workspace", eventCount > 0 ? "engaged" : "waiting"],
            ["Verification", status === "COMPLETED" ? "passed" : "armed"],
          ].map(([label, value]) => (
            <div key={label} className="rounded-xl border border-border bg-surface-2/50 px-3 py-2.5">
              <div className="flex items-center gap-2 text-xs font-semibold text-text"><span className="h-1.5 w-1.5 rounded-full bg-tc" />{label}</div>
              <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.12em] text-text-muted">{value}</p>
            </div>
          ))}
        </div>
        <ActivityTimeline items={events.slice(-8).map(eventToActivity)} empty="Waiting for the first execution event…" />
      </CardBody>
    </Card>
  );
}

function CommandCenter() {
  const { messages, addMessage, updateMessage, submitting, setSubmitting, activeTaskId } = useConversation();
  const { addTask } = useSession();
  const { state: connectionState } = useHealth();
  const { tasks } = useTasks(100);
  const connectionDown = connectionState === "disconnected";

  const activeMessage = messages.findLast?.((m) => m.taskId === activeTaskId);
  const activeStatus = activeMessage?.status;
  const orbState = submitting ? "thinking" : statusToOrb(activeStatus);

  const counts = React.useMemo(() => {
    return {
      total: tasks.length,
      active: tasks.filter((t) => t.status === "RUNNING" || t.status === "PENDING").length,
      waiting: tasks.filter((t) => t.status === "AWAITING_APPROVAL").length,
      completed: tasks.filter((t) => t.status === "COMPLETED").length,
    };
  }, [tasks]);

  const recentTasks = React.useMemo(() => tasks.slice(0, 4), [tasks]);

  const onSubmit = async (prompt: string) => {
    setSubmitting(true);
    addMessage({ role: "user", content: prompt });
    const tcId = addMessage({ role: "tc", content: "Planning the engineering run…", status: "PENDING" });
    try {
      const { summary, ownerToken } = await orchestrator.createTask(prompt);
      addTask(summary, ownerToken);
      updateMessage(tcId, {
        content:
          summary.answer ??
          (summary.status === "AWAITING_APPROVAL"
            ? "This run is waiting for your approval."
            : summary.status === "RUNNING"
              ? "Task accepted. TC is executing the engineering loop."
              : summary.error ?? "Task accepted."),
        taskId: summary.task_id,
        status: summary.status,
        error: summary.status === "FAILED",
      });
    } catch (e) {
      updateMessage(tcId, { content: calmError(e, connectionDown), error: true });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AppShell orbState={orbState}>
      <section className="relative overflow-hidden rounded-[30px] border border-border bg-surface shadow-md">
        <div className="pointer-events-none absolute inset-0 tc-command-grid" aria-hidden="true" />
        <div className="pointer-events-none absolute -right-24 -top-28 h-72 w-72 rounded-full bg-tc/10 blur-3xl" aria-hidden="true" />
        <div className="relative p-5 sm:p-7 lg:p-8">
          <div className="flex flex-col gap-7 lg:flex-row lg:items-center lg:justify-between">
            <div className="max-w-3xl">
              <div className="flex flex-wrap items-center gap-2">
                <Badge>TC ENGINEERING AI</Badge>
                <span className="rounded-pill border border-border bg-surface/80 px-2.5 py-1 font-mono text-[10px] text-text-muted">COMMAND CENTER</span>
              </div>
              <h1 className="mt-5 text-balance text-3xl font-semibold tracking-[-0.04em] text-text sm:text-5xl lg:text-6xl">
                Build the thing. <span className="tc-text-gradient">Verify the result.</span>
              </h1>
              <p className="mt-4 max-w-2xl text-sm leading-6 text-text-secondary sm:text-base">
                Creator Sir, TC turns an engineering request into a controlled execution run — planning, tools, approvals, tests, repair, and verification in one place.
              </p>
              <div className="mt-5 flex flex-wrap gap-2 text-[11px] text-text-muted">
                <span className="rounded-pill border border-border bg-surface px-2.5 py-1">Brain routed</span>
                <span className="rounded-pill border border-border bg-surface px-2.5 py-1">Sandboxed workspace</span>
                <span className="rounded-pill border border-border bg-surface px-2.5 py-1">Owner approved</span>
              </div>
            </div>
            <div className="mx-auto shrink-0 rounded-[26px] border border-tc/15 bg-surface/80 p-5 shadow-sm lg:mx-0">
              <TCOrb state={orbState} size={126} label={`TC ${orbState}`} />
              <div className="mt-3 text-center">
                <p className="text-xs font-semibold text-text">TC is {orbState === "idle" ? "ready" : orbState}</p>
                <p className="mt-1 font-mono text-[10px] text-text-muted">control plane online</p>
              </div>
            </div>
          </div>

          <div className="mt-7 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="Runs" value={String(counts.total)} detail="all recorded" />
            <Stat label="Active" value={String(counts.active)} detail="executing" tone="accent" />
            <Stat label="Waiting" value={String(counts.waiting)} detail="approval" />
            <Stat label="Verified" value={String(counts.completed)} detail="completed" tone="success" />
          </div>
        </div>
        <div className="mt-4"><MemoryPanel /></div>
      </section>

      <section className="mt-6 grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="min-w-0">
          <div className="mb-3 flex items-end justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-emerald">Engineering command</p>
              <h2 className="mt-1 text-xl font-semibold tracking-tight text-text">What are we building?</h2>
            </div>
            {activeTaskId ? <Link href={`/tasks/${activeTaskId}`}><Button variant="ghost" size="sm">Open active run <ChevronRight className="h-4 w-4" /></Button></Link> : null}
          </div>

          <div className="grid gap-2 sm:grid-cols-3">
            {starterPrompts.map(({ icon: Icon, title, text }) => (
              <button
                key={title}
                type="button"
                onClick={() => {
                  const event = new CustomEvent("tc:prefill", { detail: text });
                  window.dispatchEvent(event);
                }}
                className="group rounded-2xl border border-border bg-surface p-4 text-left shadow-xs transition duration-fast ease-spring hover:-translate-y-px hover:border-tc/30 hover:shadow-sm"
              >
                <span className="grid h-9 w-9 place-items-center rounded-xl bg-soft-green text-emerald">
                  <Icon className="h-4 w-4" />
                </span>
                <p className="mt-3 text-sm font-semibold text-text">{title}</p>
                <p className="mt-1 text-xs leading-5 text-text-muted">{text}</p>
              </button>
            ))}
          </div>

          <div className="mt-4">
            <Composer busy={submitting} onSubmit={onSubmit} />
          </div>

          <div className="mt-5">
            <ConversationView messages={messages} orbState={orbState} />
          </div>

          {activeTaskId ? <div className="mt-6"><CurrentTaskPanel taskId={activeTaskId} /></div> : null}
        </div>

        <aside className="space-y-4">
          <Card>
            <CardBody>
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-text-muted">Control plane</p>
                  <h3 className="mt-1 text-base font-semibold text-text">TC status</h3>
                </div>
                <Sparkles className="h-4 w-4 text-tc" />
              </div>
              <div className="mt-4 space-y-3">
                {[
                  ["Orchestrator", connectionState === "connected" ? "Connected" : connectionState],
                  ["Workspace", "gRPC protected"],
                  ["Approval", "Owner gated"],
                ].map(([label, value]) => (
                  <div key={label} className="flex items-center justify-between gap-4 border-b border-border pb-3 last:border-0 last:pb-0">
                    <span className="text-xs text-text-secondary">{label}</span>
                    <span className="font-mono text-[10px] text-text-muted">{value}</span>
                  </div>
                ))}
              </div>
            </CardBody>
          </Card>

          <Card>
            <CardBody>
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-text">Recent engineering runs</h3>
                <Link href="/tasks" className="font-mono text-[10px] text-emerald hover:underline">View all</Link>
              </div>
              {recentTasks.length === 0 ? (
                <div className="mt-4 rounded-xl border border-dashed border-border p-5 text-center text-xs text-text-muted">No saved runs yet.</div>
              ) : (
                <div className="mt-3 space-y-2">
                  {recentTasks.map((task) => (
                    <Link key={task.task_id} href={`/tasks/${task.task_id}`} className="block rounded-xl border border-border bg-surface-2/50 p-3 transition hover:border-tc/25 hover:bg-soft-green/40">
                      <div className="flex items-start justify-between gap-3">
                        <p className="line-clamp-2 text-xs font-medium leading-5 text-text">{task.prompt}</p>
                        <span className={`mt-1 h-2 w-2 shrink-0 rounded-full ${task.status === "COMPLETED" ? "bg-success" : task.status === "FAILED" ? "bg-error" : task.status === "AWAITING_APPROVAL" ? "bg-warning" : "bg-tc"}`} />
                      </div>
                      <p className="mt-2 font-mono text-[10px] text-text-muted">{task.task_id.slice(0, 10)} · {task.status.replaceAll("_", " ")}</p>
                    </Link>
                  ))}
                </div>
              )}
            </CardBody>
          </Card>

          <div className="rounded-2xl border border-tc/15 bg-gradient-to-br from-soft-green via-surface to-surface px-4 py-4">
            <div className="flex items-start gap-3">
              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-tc text-white"><ShieldCheck className="h-4 w-4" /></span>
              <div>
                <p className="text-xs font-semibold text-text">Why TC feels different</p>
                <p className="mt-1 text-xs leading-5 text-text-secondary">The Brain can reason, but TC owns the workflow: tools, boundaries, approvals, execution, and proof.</p>
              </div>
            </div>
          </div>
        </aside>
      </section>
    </AppShell>
  );
}

export default function HomePage() {
  return (
    <ConversationProvider>
      <CommandCenter />
    </ConversationProvider>
  );
}
