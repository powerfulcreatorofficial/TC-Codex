import { OrchestratorApiError } from "./api/orchestrator";

/**
 * Map a real backend approval error to a calm, actionable user message.
 *
 * Backend errors surface as HTTP 409 (ApprovalError: expired / already decided
 * / action mismatch / not awaiting / no pending) or 401/403 (owner auth) or
 * 5xx (unavailable). Messages correspond to the real backend behavior; no
 * stack traces are exposed.
 */
export function approvalErrorMessage(e: unknown): string {
  if (e instanceof OrchestratorApiError) {
    const detail = e.message.toLowerCase();
    if (e.status === 401 || e.status === 403)
      return "Authorization failed. Please verify your session.";
    if (detail.includes("expired")) return "Approval expired. Refresh the approval list.";
    if (detail.includes("already") || detail.includes("consumed") || detail.includes("decided"))
      return "Approval was already processed.";
    if (detail.includes("mismatch")) return "This approval no longer matches the pending action.";
    if (detail.includes("not awaiting") || detail.includes("no pending"))
      return "This task is no longer awaiting approval.";
    if (e.status >= 500) return "TC is temporarily unavailable. Please try again.";
    return "Couldn't process this approval. Please try again.";
  }
  return "Network error. Please check your connection and try again.";
}

/** Connection-level error message for loading the approval list. */
export function approvalLoadErrorMessage(e: unknown): string {
  if (e instanceof OrchestratorApiError && e.status >= 500)
    return "Unable to load approvals. Check the connection and retry.";
  if (e instanceof OrchestratorApiError && (e.status === 401 || e.status === 403))
    return "Authorization failed. Please verify your session.";
  return "Unable to load approvals. Check the connection and retry.";
}
