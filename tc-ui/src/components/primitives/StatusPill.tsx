import { cn } from "@/lib/cn";
import type { TaskStatus } from "@/lib/api/orchestrator";

type Status = TaskStatus;

const statusConfig: Record<
  Status,
  { label: string; dot: string; text: string; bg: string; border: string }
> = {
  PENDING: {
    label: "Pending",
    dot: "bg-text-muted",
    text: "text-text-secondary",
    bg: "bg-surface-2",
    border: "border-border",
  },
  RUNNING: {
    label: "Running",
    dot: "bg-tc",
    text: "text-emerald",
    bg: "bg-soft-green",
    border: "border-tc/20",
  },
  AWAITING_APPROVAL: {
    label: "Awaiting approval",
    dot: "bg-warning",
    text: "text-warning",
    bg: "bg-warning/10",
    border: "border-warning/20",
  },
  COMPLETED: {
    label: "Completed",
    dot: "bg-success",
    text: "text-success",
    bg: "bg-success/10",
    border: "border-success/20",
  },
  FAILED: {
    label: "Failed",
    dot: "bg-error",
    text: "text-error",
    bg: "bg-error/10",
    border: "border-error/20",
  },
};

export interface StatusPillProps {
  status: Status;
  className?: string;
  withDot?: boolean;
  /** Pulsing dot for active states. */
  animated?: boolean;
}

export function StatusPill({ status, className, withDot = true, animated }: StatusPillProps) {
  const cfg = statusConfig[status];
  const live = animated && (status === "RUNNING" || status === "AWAITING_APPROVAL");
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-pill border px-2.5 py-1 text-xs font-medium",
        cfg.bg,
        cfg.text,
        cfg.border,
        className,
      )}
      role="status"
    >
      {withDot ? (
        <span
          className={cn("h-1.5 w-1.5 rounded-full", cfg.dot, live && "animate-pulse")}
          aria-hidden="true"
        />
      ) : null}
      {cfg.label}
    </span>
  );
}
