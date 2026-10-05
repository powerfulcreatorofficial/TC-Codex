"use client";

import * as React from "react";
import Link from "next/link";
import { AppShell } from "@/components/shell/AppShell";
import { TaskRow } from "@/components/signature/TaskRow";
import { Card, CardBody, Button, Skeleton } from "@/components/primitives";
import { useSession } from "@/lib/session";
import { useTasks } from "@/lib/hooks/use-api";
import { cn } from "@/lib/cn";
import type { TaskStatus, TaskSummary } from "@/lib/api/orchestrator";

type Filter = "all" | "active" | "waiting" | "completed" | "failed";
const FILTERS: { id: Filter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "active", label: "Active" },
  { id: "waiting", label: "Waiting" },
  { id: "completed", label: "Completed" },
  { id: "failed", label: "Failed" },
];

function matches(status: TaskStatus, f: Filter): boolean {
  if (f === "active") return status === "RUNNING" || status === "PENDING";
  if (f === "waiting") return status === "AWAITING_APPROVAL";
  if (f === "completed") return status === "COMPLETED";
  if (f === "failed") return status === "FAILED";
  return true;
}

function Row({ task }: { task: TaskSummary }) {
  return (
    <Link href={`/tasks/${task.task_id}`}>
      <TaskRow
        taskId={task.task_id}
        prompt={task.prompt}
        status={task.status}
        currentStep={task.current_step}
        maxSteps={task.max_steps}
        createdAt={task.created_at}
        updatedAt={task.updated_at}
      />
    </Link>
  );
}

export default function TasksPage() {
  const { tasks: persistedTasks, loading, error, refresh } = useTasks();
  const { tasks: sessionTasks } = useSession();
  const [filter, setFilter] = React.useState<Filter>("all");
  const [refreshing, setRefreshing] = React.useState(false);

  const refreshAll = async () => {
    setRefreshing(true);
    await refresh();
    setRefreshing(false);
  };

  // Prefer server truth; merge the just-created in-memory summary if the list endpoint lags.
  const merged = React.useMemo(() => {
    const byId = new Map(persistedTasks.map((task) => [task.task_id, task]));
    for (const session of sessionTasks) byId.set(session.taskId, session.summary);
    return Array.from(byId.values()).sort((a, b) =>
      (b.updated_at ?? b.created_at ?? "").localeCompare(a.updated_at ?? a.created_at ?? ""),
    );
  }, [persistedTasks, sessionTasks]);
  const visible = merged.filter((task) => matches(task.status, filter));

  return (
    <AppShell>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-text">Tasks</h1>
          <p className="mt-1 text-xs text-text-muted">Persistent engineering history from TC.</p>
        </div>
        <Button variant="ghost" size="sm" onClick={refreshAll} loading={refreshing}>
          Refresh
        </Button>
      </div>

      {error ? (
        <p className="mt-3 rounded-md bg-error/10 px-3 py-2 text-xs text-error" role="alert">
          {error}
        </p>
      ) : null}

      <div className="mt-4 flex flex-wrap gap-2">
        {FILTERS.map((f) => (
          <button
            key={f.id}
            type="button"
            onClick={() => setFilter(f.id)}
            aria-pressed={filter === f.id}
            className={cn(
              "tap-target rounded-pill border px-3 py-1 text-xs font-medium transition",
              filter === f.id
                ? "border-tc bg-soft-green text-emerald"
                : "border-border bg-surface text-text-secondary hover:bg-surface-2",
            )}
          >
            {f.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="mt-4 space-y-2">
          {[1, 2, 3].map((n) => <Skeleton key={n} className="h-16 w-full rounded-lg" />)}
        </div>
      ) : visible.length === 0 ? (
        <Card className="mt-4">
          <CardBody className="py-12 text-center">
            <p className="text-sm text-text-secondary">{merged.length ? "No tasks match this filter." : "No tasks yet."}</p>
            <Link href="/" className="mt-3 inline-block">
              <Button variant="primary" size="sm">Start a new task</Button>
            </Link>
          </CardBody>
        </Card>
      ) : (
        <div className="mt-4 space-y-2">
          {visible.map((task) => <Row key={task.task_id} task={task} />)}
        </div>
      )}
    </AppShell>
  );
}
