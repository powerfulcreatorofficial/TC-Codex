"use client";

import * as React from "react";
import Link from "next/link";
import { AppShell } from "@/components/shell/AppShell";
import { Card, CardBody, Button } from "@/components/primitives";
import { ApprovalCard } from "@/components/signature/ApprovalCard";
import { orchestrator, OrchestratorApiError, type ApprovalView } from "@/lib/api/orchestrator";
import { useSession } from "@/lib/session";
import { approvalErrorMessage, approvalLoadErrorMessage } from "@/lib/approval-errors";

/**
 * Approvals queue.
 *
 * The backend exposes NO global approvals endpoint (verified). The UI therefore
 * shows the REAL tasks in THIS session that are AWAITING_APPROVAL, fetches each
 * pending approval via GET /v1/tasks/{id}/pending_approval (owner-gated), and
 * wires approve/reject to the real API. Only the session that created a task
 * holds its owner token (in memory, never persisted/logged).
 */

interface ApprovalState {
  view: ApprovalView | null;
  loading: boolean;
  loadError: string | null;
  deciding: boolean;
  actionError: string | null;
  decided: "approved" | "rejected" | null;
}

export default function ApprovalsPage() {
  const { awaitingApprovals, ownerOf, updateTask } = useSession();
  const [states, setStates] = React.useState<Record<string, ApprovalState>>({});
  const [connectionError, setConnectionError] = React.useState<string | null>(null);
  const [refreshing, setRefreshing] = React.useState(false);

  const loadAll = React.useCallback(
    async (showRefreshing = false) => {
      if (showRefreshing) setRefreshing(true);
      setConnectionError(null);
      let anyConnFail = false;
      await Promise.all(
        awaitingApprovals.map(async (t) => {
          const token = ownerOf(t.taskId);
          if (!token) {
            setStates((p) => ({
              ...p,
              [t.taskId]: {
                view: null,
                loading: false,
                loadError: null,
                deciding: false,
                actionError: null,
                decided: null,
              },
            }));
            return;
          }
          setStates((p) => ({
            ...p,
            [t.taskId]: {
              view: p[t.taskId]?.view ?? null,
              loading: true,
              loadError: null,
              deciding: false,
              actionError: null,
              decided: p[t.taskId]?.decided ?? null,
            },
          }));
          try {
            const a = await orchestrator.getPendingApproval(t.taskId, token);
            setStates((p) => ({
              ...p,
              [t.taskId]: {
                view: a,
                loading: false,
                loadError: null,
                deciding: false,
                actionError: null,
                decided: null,
              },
            }));
          } catch (e) {
            if (e instanceof OrchestratorApiError && (e.status === 401 || e.status === 403))
              anyConnFail = true;
            if (e instanceof OrchestratorApiError && e.status >= 500) anyConnFail = true;
            setStates((p) => ({
              ...p,
              [t.taskId]: {
                view: null,
                loading: false,
                loadError: approvalLoadErrorMessage(e),
                deciding: false,
                actionError: null,
                decided: null,
              },
            }));
          }
        }),
      );
      if (anyConnFail)
        setConnectionError("Unable to load approvals. Check the connection and retry.");
      if (showRefreshing) setRefreshing(false);
    },
    [awaitingApprovals, ownerOf],
  );

  React.useEffect(() => {
    loadAll();
  }, [loadAll]);

  const decide = async (taskId: string, approved: boolean) => {
    const st = states[taskId];
    const token = ownerOf(taskId);
    if (!st?.view || !token || st.deciding || st.decided) return; // prevent duplicate
    // Optimistic: disable + show pending.
    setStates((p) => ({
      ...p,
      [taskId]: { ...p[taskId], deciding: true, actionError: null },
    }));
    try {
      const updated = await orchestrator.approve(
        taskId,
        { approved, nonce: st.view.nonce, decided_by: "creator" },
        token,
      );
      // Confirm via server response; reconcile task state.
      updateTask(taskId, updated);
      setStates((p) => ({
        ...p,
        [taskId]: {
          ...p[taskId],
          deciding: false,
          decided: approved ? "approved" : "rejected",
          actionError: null,
        },
      }));
    } catch (e) {
      // Roll back: keep approval, show calm error.
      setStates((p) => ({
        ...p,
        [taskId]: {
          ...p[taskId],
          deciding: false,
          decided: null,
          actionError: approvalErrorMessage(e),
        },
      }));
    }
  };

  return (
    <AppShell>
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold tracking-tight text-text">Approvals</h1>
        {awaitingApprovals.length > 0 ? (
          <Button variant="ghost" size="sm" onClick={() => loadAll(true)} loading={refreshing}>
            Refresh
          </Button>
        ) : null}
      </div>
      <p className="mt-1 text-xs text-text-muted">
        Mutating actions pause here for your approval. Only the task owner can approve.
      </p>

      {connectionError ? (
        <p className="mt-2 rounded-md bg-error/10 px-3 py-2 text-xs text-error" role="alert">
          {connectionError}
        </p>
      ) : null}

      {awaitingApprovals.length === 0 ? (
        <Card className="mt-4">
          <CardBody className="py-12 text-center">
            <p className="text-sm text-text-secondary">No pending approvals.</p>
            <Link href="/" className="mt-3 inline-block">
              <Button variant="secondary" size="sm">
                Start a task
              </Button>
            </Link>
          </CardBody>
        </Card>
      ) : (
        <div className="mt-4 space-y-4">
          {awaitingApprovals.map((t) => {
            const st = states[t.taskId];
            const token = ownerOf(t.taskId);
            return st?.view ? (
              <ApprovalCard
                key={t.taskId}
                toolName={st.view.tool_name}
                riskLevel={st.view.risk_level}
                argumentsSummary={st.view.arguments_metadata}
                createdAt={st.view.created_at}
                expiresAt={st.view.expires_at}
                nonce={st.view.nonce}
                authorized={!!token}
                deciding={st.deciding}
                actionError={st.actionError}
                decided={st.decided}
                onApprove={() => decide(t.taskId, true)}
                onReject={() => decide(t.taskId, false)}
              >
                <Link
                  href={`/tasks/${t.taskId}`}
                  className="mt-2 block font-mono text-xs text-text-muted hover:text-text"
                >
                  {t.taskId.slice(0, 12)} · {t.summary.prompt}
                </Link>
              </ApprovalCard>
            ) : st?.loadError ? (
              <Card key={t.taskId}>
                <CardBody>
                  <p className="text-sm text-text-secondary">{t.summary.prompt}</p>
                  <p className="mt-1 text-xs text-error">{st.loadError}</p>
                </CardBody>
              </Card>
            ) : (
              <Card key={t.taskId}>
                <CardBody className="text-sm text-text-secondary">Loading approval…</CardBody>
              </Card>
            );
          })}
        </div>
      )}
    </AppShell>
  );
}
