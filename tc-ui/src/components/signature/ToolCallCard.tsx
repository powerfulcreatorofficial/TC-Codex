import { cn } from "@/lib/cn";
import { Badge, Card } from "../primitives";

export type ToolStatus = "requested" | "approved" | "running" | "success" | "error" | "rejected";

const statusTone: Record<
  ToolStatus,
  "neutral" | "green" | "teal" | "warning" | "error" | "success"
> = {
  requested: "neutral",
  approved: "teal",
  running: "green",
  success: "success",
  error: "error",
  rejected: "error",
};

export interface ToolCallCardProps {
  name: string;
  /** Risk level (matches backend policy: L0/L1/L2). */
  riskLevel?: string;
  status: ToolStatus;
  /** A redacted, safe summary of arguments — never raw secrets. */
  argumentsSummary?: Record<string, unknown>;
  /** Redacted output preview. */
  output?: string;
  durationMs?: number;
  className?: string;
}

export function ToolCallCard({
  name,
  riskLevel,
  status,
  argumentsSummary,
  output,
  durationMs,
  className,
}: ToolCallCardProps) {
  const entries = argumentsSummary ? Object.entries(argumentsSummary) : [];
  return (
    <Card className={cn("p-4", className)}>
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <code className="rounded-md bg-surface-2 px-2 py-1 font-mono text-sm font-medium text-text">
            {name}
          </code>
          {riskLevel ? (
            <Badge tone={riskLevel === "L0" ? "neutral" : "green"}>{riskLevel}</Badge>
          ) : null}
        </div>
        <Badge tone={statusTone[status]}>{status}</Badge>
      </div>

      {entries.length > 0 ? (
        <dl className="mt-3 space-y-1.5">
          {entries.map(([k, v]) => (
            <div key={k} className="flex gap-2 text-xs">
              <dt className="shrink-0 font-mono text-text-muted">{k}</dt>
              <dd className="min-w-0 truncate font-mono text-text-secondary">
                {typeof v === "string" ? v : JSON.stringify(v)}
              </dd>
            </div>
          ))}
        </dl>
      ) : null}

      {output ? (
        <pre className="scrollbar-thin mt-3 max-h-32 overflow-auto rounded-md bg-surface-2 p-2.5 font-mono text-xs text-text-secondary">
          {output}
        </pre>
      ) : null}

      {typeof durationMs === "number" ? (
        <p className="mt-2 text-xs text-text-muted">{durationMs} ms</p>
      ) : null}
    </Card>
  );
}
