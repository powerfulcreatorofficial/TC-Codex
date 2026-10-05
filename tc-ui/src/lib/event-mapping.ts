import type { TaskEvent } from "@/lib/api/orchestrator";
import type { ActivityItem } from "@/components/signature/ActivityTimeline";
import type { OrbState } from "@/components/signature/TCOrb";
import type { TaskStatus } from "@/lib/api/orchestrator";

/**
 * Maps the REAL backend event_type values (from tc-orchestrator api.py) to
 * timeline tones and human labels. No event names are invented.
 */
const EVENT_META: Record<string, { tone: ActivityItem["tone"]; label: string }> = {
  task_started: { tone: "green", label: "Task started" },
  task_completed: { tone: "success", label: "Task completed" },
  task_failed: { tone: "error", label: "Task failed" },
  approval_requested: { tone: "warning", label: "Approval requested" },
  approval_decided: { tone: "teal", label: "Approval decided" },
};

export function eventToActivity(e: TaskEvent): ActivityItem {
  const meta = EVENT_META[e.event_type] ?? { tone: "neutral" as const, label: e.event_type };
  const toolPart = e.tool_name ? `${e.tool_name} · ` : "";
  const statusPart = e.status ? ` · ${e.status}` : "";
  return {
    id: e.id,
    title: `${meta.label}${toolPart ? ` — ${toolPart.slice(0, -3)}` : ""}`,
    meta: `${e.ts}${statusPart}`,
    tone: meta.tone,
  };
}

/** Maps a task status to a TC Orb state. Derived from real backend state. */
export function statusToOrb(status: TaskStatus | undefined): OrbState {
  switch (status) {
    case "RUNNING":
      return "executing";
    case "AWAITING_APPROVAL":
      return "waiting";
    case "COMPLETED":
      return "success";
    case "FAILED":
      return "error";
    case "PENDING":
      return "thinking";
    default:
      return "idle";
  }
}
