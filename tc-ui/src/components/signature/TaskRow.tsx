import { cn } from "@/lib/cn";
import { StatusPill } from "../primitives/StatusPill";
import { formatRelative } from "@/lib/format";
import type { TaskStatus } from "@/lib/api/orchestrator";

export interface TaskRowProps {
  taskId: string;
  prompt: string;
  status: TaskStatus;
  /** Current step / max steps. */
  currentStep?: number;
  maxSteps?: number;
  /** ISO timestamp from the backend. */
  createdAt?: string | null;
  updatedAt?: string | null;
  onClick?: () => void;
  className?: string;
}

export function TaskRow({
  taskId,
  prompt,
  status,
  currentStep,
  maxSteps,
  createdAt,
  updatedAt,
  onClick,
  className,
}: TaskRowProps) {
  const live = status === "RUNNING" || status === "AWAITING_APPROVAL";
  const Row = onClick ? "button" : "div";
  const stepPart =
    typeof currentStep === "number" && typeof maxSteps === "number"
      ? `· step ${currentStep}/${maxSteps}`
      : "";
  const timePart = updatedAt
    ? `· updated ${formatRelative(updatedAt)}`
    : createdAt
      ? `· ${formatRelative(createdAt)}`
      : "";
  return (
    <Row
      type={onClick ? "button" : undefined}
      onClick={onClick}
      className={cn(
        "flex w-full items-center gap-3 rounded-lg border border-border bg-surface px-4 py-3 text-left",
        "transition duration-fast ease-spring",
        onClick && "hover:border-border-strong hover:shadow-sm focus-visible:shadow-glow",
        className,
      )}
    >
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-text">{prompt}</p>
        <p className="mt-0.5 truncate font-mono text-xs text-text-muted">
          {taskId.slice(0, 10)} {stepPart} {timePart}
        </p>
      </div>
      <StatusPill status={status} animated={live} />
    </Row>
  );
}
