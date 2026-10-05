"use client";

import * as React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { AppShell } from "@/components/shell/AppShell";
import { Card, CardBody, StatusPill, Button, Spinner, Skeleton } from "@/components/primitives";
import { ActivityTimeline } from "@/components/signature/ActivityTimeline";
import { ApprovalCard } from "@/components/signature/ApprovalCard";
import { ToolCallCard } from "@/components/signature/ToolCallCard";
import {
  orchestrator,
  OrchestratorApiError,
  type ApprovalView,
  type TaskEvent,
  type TaskEvaluation,
  type TaskRecovery,
} from "@/lib/api/orchestrator";
import { useTask, useEventStream } from "@/lib/hooks/use-api";
import { useSession } from "@/lib/session";
import { statusToOrb, eventToActivity } from "@/lib/event-mapping";
import { formatTime } from "@/lib/format";

export default function TaskDetailPage() {
  const params = useParams<{ id: string }>();
  const taskId = params.id;
  const { ownerOf, updateTask } = useSession();
  const ownerToken = ownerOf(taskId);

  const { summary, loading, error } = useTask(taskId);
  const { events } = useEventStream(taskId, true);
  const [evaluation, setEvaluation] = React.useState<TaskEvaluation | null>(null);
  const [recovery, setRecovery] = React.useState<TaskRecovery | null>(null);

  React.useEffect(() => {
    let active = true;
    if (!summary || (summary.status !== "COMPLETED" && summary.status !== "FAILED")) {
      setEvaluation(null);
      return;
    }
    orchestrator.getTaskEvaluation(taskId).then((value) => {
      if (active) setEvaluation(value);
    }).catch(() => {
      if (active) setEvaluation(null);
    });
    return () => { active = false; };
  }, [summary?.status, taskId]);

  React.useEffect(() => {
    let active = true;
    if (!summary || (summary.status !== "FAILED" && summary.status !== "AWAITING_APPROVAL")) {
      setRecovery(null);
      return;
    }
    orchestrator.getTaskRecovery(taskId).then((value) => {
      if (active) setRecovery(value);
    }).catch(() => {
      if (active) setRecovery(null);
    });
    return () => { active = false; };
  }, [summary?.status, taskId]);

  // Real events that carry a tool_name → render as tool-call cards.
  const toolEvents: TaskEvent[] = events.filter((e) => !!e.tool_name);

  function toolStatusFor(e: TaskEvent): "requested" | "success" | "error" | "approved" {
    if (e.event_type === "task_failed" || e.status === "failed" || e.status === "rejected")
      return "error";
    if (e.event_type === "task_completed" || e.status === "approved") return "approved";
    if (e.event_type === "approval_decided") return "approved";
    return "success";
  }

  const [approval, setApproval] = React.useState<ApprovalView | null>(null);
  const [approvalError, setApprovalError] = React.useState<string | null>(null);
  const [deciding, setDeciding] = React.useState(false);

  // Fetch the pending approval (owner-gated) when the task is awaiting.
  React.useEffect(() => {
    let active = true;
    if (summary?.status !== "AWAITING_APPROVAL" || !ownerToken) {
      setApproval(null);
      return;
    }
    (async () => {
      try {
        const a = await orchestrator.getPendingApproval(taskId, ownerToken);
        if (active) {
          setApproval(a);
          setApprovalError(null);
        }
      } catch (e) {
        if (active)
          setApprovalError(e instanceof OrchestratorApiError ? e.message : "no pending approval");
      }
    })();
    return () => {
      active = false;
    };
  }, [taskId, summary?.status, ownerToken]);

  React.useEffect(() => {
    if (summary) updateTask(taskId, summary);
  }, [summary, taskId, updateTask]);

  const decide = async (approved: boolean) => {
    if (!approval || !ownerToken) return;
    setDeciding(true);
    try {
      const updated = await orchestrator.approve(
        taskId,
        { approved, nonce: approval.nonce, decided_by: "creator" },
        ownerToken,
      );
      updateTask(taskId, updated);
      setApproval(null);
    } catch (e) {
      setApprovalError(e instanceof OrchestratorApiError ? e.message : "approval failed");
    } finally {
      setDeciding(false);
    }
  };

  if (loading && !summary) {
    return (
      <AppShell>
        <Skeleton className="h-6 w-1/2" />
        <Skeleton className="mt-3 h-20 w-full" />
        <Skeleton className="mt-3 h-40 w-full" />
      </AppShell>
    );
  }

  if (error && !summary) {
    return (
      <AppShell>
        <Card>
          <CardBody className="text-center">
            <p className="text-sm text-error">Task not found.</p>
            <div className="mt-3 flex justify-center gap-3">
              <Link href="/tasks">
                <Button variant="secondary" size="sm">
                  Back to tasks
                </Button>
              </Link>
              <Link href="/">
                <Button variant="ghost" size="sm">
                  Command Center
                </Button>
              </Link>
            </div>
          </CardBody>
        </Card>
      </AppShell>
    );
  }

  return (
    <AppShell orbState={statusToOrb(summary?.status)}>
      <div className="flex items-center gap-2">
        <Link href="/tasks">
          <Button variant="ghost" size="sm">
            ← Tasks
          </Button>
        </Link>
        <Link href="/">
          <Button variant="ghost" size="sm">
            Command Center
          </Button>
        </Link>
      </div>

      <h1 className="mt-2 text-xl font-semibold tracking-tight text-text">Task detail</h1>

      <Card className="mt-3">
        <CardBody>
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="truncate text-sm font-medium text-text">{summary?.prompt}</p>
              <p className="mt-1 font-mono text-xs text-text-muted">
                {taskId.slice(0, 16)} · step {summary?.current_step}/{summary?.max_steps}
              </p>
              <p className="mt-1 text-xs text-text-muted">
                {summary?.created_at ? `Created ${formatTime(summary.created_at)}` : null}
                {summary?.updated_at ? ` · Updated ${formatTime(summary.updated_at)}` : null}
              </p>
            </div>
            <StatusPill status={summary?.status ?? "PENDING"} animated />
          </div>

          {summary?.status === "COMPLETED" && summary.answer ? (
            <div className="mt-4 break-words rounded-md bg-surface-2 p-3 text-sm text-text-secondary">
              {summary.answer}
            </div>
          ) : null}
          {summary?.status === "FAILED" && summary.error ? (
            <div className="mt-4 break-words rounded-md bg-error/10 p-3 text-sm text-error">
              {summary.error}
            </div>
          ) : null}
        </CardBody>
      </Card>

      {/* Approval state — driven by the real backend, owner-gated */}
      {summary?.status === "AWAITING_APPROVAL" ? (
        approval ? (
          <ApprovalCard
            className="mt-4"
            toolName={approval.tool_name}
            riskLevel={approval.risk_level}
            argumentsSummary={approval.arguments_metadata}
            expiresAt={approval.expires_at}
            nonce={approval.nonce}
            authorized={!!ownerToken}
            deciding={deciding}
            onApprove={() => decide(true)}
            onReject={() => decide(false)}
          />
        ) : ownerToken ? (
          <Card className="mt-4">
            <CardBody className="flex items-center gap-3 text-sm text-text-secondary">
              <Spinner size="sm" /> Loading approval…
            </CardBody>
          </Card>
        ) : (
          <Card className="mt-4">
            <CardBody>
              <p className="text-sm text-error">
                This task requires approval, but the owner token is not available in this session.
                Only the session that created the task can approve it.
              </p>
            </CardBody>
          </Card>
        )
      ) : null}
      {approvalError ? <p className="mt-2 text-xs text-text-muted">{approvalError}</p> : null}

      {recovery ? (
        <section className="mt-4">
          <div className="mb-2 flex items-end justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-emerald">Recovery</p>
              <h2 className="mt-1 text-sm font-semibold text-text">Adaptive execution guidance</h2>
            </div>
            <span className="font-mono text-[11px] text-text-muted">{recovery.repair_attempts}/{recovery.max_repair_attempts} repair signals</span>
          </div>
          <Card>
            <CardBody>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-sm font-medium text-text">{recovery.recovery_class.replaceAll("_", " ")}</p>
                  <p className="mt-1 text-xs text-text-secondary">{recovery.recommended_action}</p>
                </div>
                <StatusPill status={recovery.retry_allowed ? "RUNNING" : "FAILED"} />
              </div>
              <div className="mt-3 space-y-1">
                {recovery.evidence.map((item) => <p key={item} className="text-[10px] text-text-muted">• {item}</p>)}
              </div>
            </CardBody>
          </Card>
        </section>
      ) : null}

      {evaluation ? (
        <section className="mt-4">
          <div className="mb-2 flex items-end justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-emerald">Evidence review</p>
              <h2 className="mt-1 text-sm font-semibold text-text">Execution quality</h2>
            </div>
            <span className="font-mono text-lg font-semibold text-text">{evaluation.overall_score}/100</span>
          </div>
          <Card>
            <CardBody className="space-y-3">
              {evaluation.dimensions.map((dimension) => (
                <div key={dimension.key}>
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-xs font-medium text-text">{dimension.label}</span>
                    <span className="font-mono text-[10px] text-text-muted">{dimension.score}</span>
                  </div>
                  <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-surface-2">
                    <div className="h-full rounded-full bg-tc" style={{ width: `${dimension.score}%` }} />
                  </div>
                  <p className="mt-1 text-[10px] leading-4 text-text-muted">{dimension.evidence}</p>
                </div>
              ))}
              <p className="border-t border-border pt-3 text-[10px] text-text-muted">Deterministic execution evidence, not an LLM opinion about answer quality.</p>
            </CardBody>
          </Card>
        </section>
      ) : null}

      {/* Tool-call activity from real events (events carrying a tool_name) */}
      {toolEvents.length > 0 ? (
        <section className="mt-4">
          <h2 className="mb-2 text-sm font-semibold text-text">Tool activity</h2>
          <div className="space-y-3">
            {toolEvents.map((e) => (
              <ToolCallCard
                key={e.id}
                name={e.tool_name ?? "tool"}
                riskLevel={undefined}
                status={toolStatusFor(e)}
                argumentsSummary={
                  (e.arguments_metadata as Record<string, unknown> | null) ?? undefined
                }
                output={
                  e.result_metadata ? JSON.stringify(e.result_metadata).slice(0, 240) : undefined
                }
              />
            ))}
          </div>
        </section>
      ) : null}

      {/* Activity timeline from real events */}
      <div className="mt-4">
        <ActivityTimeline
          title="Activity"
          items={events.map(eventToActivity)}
          empty="No events recorded yet."
        />
      </div>
    </AppShell>
  );
}
