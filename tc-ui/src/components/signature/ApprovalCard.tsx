"use client";

import * as React from "react";
import { cn } from "@/lib/cn";
import { Badge, Button, Card } from "../primitives";
import { Sheet } from "../primitives/Sheet";
import { formatTime, formatRelative } from "@/lib/format";

export interface ApprovalCardProps {
  toolName: string;
  riskLevel: string;
  /** Redacted, safe-to-show argument summary (never raw secrets). */
  argumentsSummary: Record<string, unknown>;
  /** ISO timestamps from the backend. */
  createdAt?: string;
  /** ISO expiry timestamp from the backend. */
  expiresAt: string;
  /** The exact pending action nonce (used only for the real API call; never
   *  displayed as a credential). */
  nonce: string;
  /** Whether the approver is authorized (holds the owner token). */
  authorized?: boolean;
  onApprove?: () => void;
  onReject?: () => void;
  /** Show a pending decision indicator (optimistic submission state). */
  deciding?: boolean;
  /** Calm error message from the last approve/reject attempt, if any. */
  actionError?: string | null;
  /** Whether the approval was just successfully decided (terminal UI state). */
  decided?: "approved" | "rejected" | null;
  className?: string;
  children?: React.ReactNode;
}

function isExpired(iso: string): boolean {
  const d = new Date(iso);
  return !Number.isNaN(d.getTime()) && d.getTime() < Date.now();
}

/**
 * Approval card for the AWAITING_APPROVAL workflow. Surfaces a redacted action
 * summary and Approve/Reject controls wired to the real API. The frontend only
 * renders what the backend returns; it never manufactures approvals or nonces.
 */
export function ApprovalCard({
  toolName,
  riskLevel,
  argumentsSummary,
  createdAt,
  expiresAt,
  authorized = true,
  onApprove,
  onReject,
  deciding,
  actionError,
  decided,
  className,
  children,
}: ApprovalCardProps) {
  const entries = Object.entries(argumentsSummary);
  const expired = isExpired(expiresAt);
  const [detailOpen, setDetailOpen] = React.useState(false);

  return (
    <Card
      className={cn("overflow-hidden border-warning/30", className)}
      role="region"
      aria-label={`Approval request for ${toolName}`}
    >
      <div className="flex items-center justify-between gap-3 border-b border-border bg-warning/5 px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-text">Approval required</span>
          <Badge tone={riskLevel === "L2" ? "error" : "warning"}>{riskLevel}</Badge>
        </div>
        <span className="text-xs text-text-muted" title={expiresAt}>
          {expired ? "expired" : `expires ${formatRelative(expiresAt)}`}
        </span>
      </div>

      <div className="p-4">
        <div className="flex items-center gap-2">
          <code className="rounded-md bg-surface-2 px-2 py-1 font-mono text-sm font-medium text-text">
            {toolName}
          </code>
          <Button variant="ghost" size="sm" onClick={() => setDetailOpen(true)}>
            Details
          </Button>
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

        {createdAt ? (
          <p className="mt-2 text-xs text-text-muted">Requested {formatTime(createdAt)}</p>
        ) : null}

        {children}

        {/* Status announcement (accessible, not color-only) */}
        {decided ? (
          <p
            role="status"
            aria-live="polite"
            className={cn(
              "mt-3 rounded-md px-3 py-2 text-xs font-medium",
              decided === "approved" ? "bg-success/10 text-success" : "bg-error/10 text-error",
            )}
          >
            {decided === "approved" ? "Approved — TC is resuming." : "Rejected — task ended."}
          </p>
        ) : null}

        {actionError ? (
          <p role="alert" className="mt-3 rounded-md bg-error/10 px-3 py-2 text-xs text-error">
            {actionError}
          </p>
        ) : null}

        {authorized && !decided ? (
          <div className="mt-4 flex gap-3">
            <Button
              variant="primary"
              size="sm"
              loading={deciding}
              disabled={deciding || expired}
              onClick={onApprove}
              aria-label={`Approve ${toolName}`}
            >
              Approve
            </Button>
            <Button
              variant="secondary"
              size="sm"
              loading={deciding}
              disabled={deciding}
              onClick={onReject}
              aria-label={`Reject ${toolName}`}
            >
              Reject
            </Button>
          </div>
        ) : !authorized ? (
          <p className="mt-4 text-xs text-error">
            Not authorized to approve this action. Only the task owner can approve.
          </p>
        ) : null}
      </div>

      {/* Detail sheet (mobile bottom-sheet / desktop side panel) — full args,
          no truncation; still only redacted backend data, no secrets. */}
      <Sheet open={detailOpen} onOpenChange={setDetailOpen} title="Approval detail" side="bottom">
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <code className="rounded-md bg-surface-2 px-2 py-1 font-mono text-sm font-medium text-text">
              {toolName}
            </code>
            <Badge tone={riskLevel === "L2" ? "error" : "warning"}>{riskLevel}</Badge>
          </div>
          <dl className="space-y-1.5">
            {entries.map(([k, v]) => (
              <div key={k} className="flex gap-2 text-xs">
                <dt className="shrink-0 font-mono text-text-muted">{k}</dt>
                <dd className="min-w-0 break-words font-mono text-text-secondary">
                  {typeof v === "string" ? v : JSON.stringify(v)}
                </dd>
              </div>
            ))}
          </dl>
          <div className="text-xs text-text-muted">
            {createdAt ? <p>Requested {formatTime(createdAt)}</p> : null}
            <p className={cn(expired && "text-error")}>
              {expired ? "Expired" : "Expires"} {formatTime(expiresAt)}
            </p>
          </div>
        </div>
      </Sheet>
    </Card>
  );
}
