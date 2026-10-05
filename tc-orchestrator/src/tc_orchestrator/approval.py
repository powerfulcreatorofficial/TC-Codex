"""Approval request/decision models and security helpers.

Security properties:
- An approval references the EXACT pending action via a single-use nonce.
- Nonces are not reusable (a replayed/repeated approval is rejected).
- Stale approvals (past ``expires_at``) are rejected.
- Approvals for a different tool/action are rejected.
- Approvals after task completion/failure are rejected.
- The Brain cannot approve its own request: approval is an external HTTP call
  requiring the task's owner token (which the Brain never receives).
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


def new_nonce() -> str:
    """A fresh, unpredictable single-use nonce."""
    return secrets.token_urlsafe(24)


def new_owner_token() -> str:
    """A fresh owner token returned to the task creator (never the Brain)."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Store only the SHA-256 of an owner token; never the raw token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class ApprovalRequest:
    """A pending approval persisted to the DB and surfaced to the approver."""

    task_id: str
    tool_name: str
    arguments_metadata: dict  # redacted, safe-to-show summary
    risk_level: str  # "L1" | "L2"
    nonce: str
    created_at: datetime
    expires_at: datetime

    def is_expired(self, now: datetime | None = None) -> bool:
        return (now or utcnow()) >= self.expires_at

    def safe_view(self) -> dict:
        """The redacted, secret-free representation shown to the approver."""
        return {
            "task_id": self.task_id,
            "tool_name": self.tool_name,
            "arguments_metadata": self.arguments_metadata,
            "risk_level": self.risk_level,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
        }


@dataclass(frozen=True)
class ApprovalDecision:
    """An external approve/reject decision."""

    task_id: str
    nonce: str
    approved: bool
    decided_by: str


class ApprovalError(Exception):
    """Base for approval security violations."""


class ApprovalNotFoundError(ApprovalError):
    pass


class ApprovalExpiredError(ApprovalError):
    pass


class ApprovalAlreadyDecidedError(ApprovalError):
    pass


class ApprovalActionMismatchError(ApprovalError):
    pass


def expiry_from_now(seconds: int, now: datetime | None = None) -> datetime:
    return (now or utcnow()) + timedelta(seconds=seconds)
