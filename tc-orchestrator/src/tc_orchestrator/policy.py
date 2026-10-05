"""Centralized approval/security policy.

Classifies tools by permission level and decides whether a requested tool
requires external approval before execution. The Brain can never bypass this:
the orchestrator consults the policy for every tool call.

Levels:
  L0 — read-only / safe              -> execute immediately
  L1 — mutating, workspace-scoped    -> require approval (when enabled)
  L2 — higher-risk / system-wide     -> require approval (always; future tools)
"""

from __future__ import annotations

from dataclasses import dataclass

from .tool_registry import Permission, ToolRegistry


@dataclass(frozen=True)
class ApprovalPolicy:
    """Configurable approval policy.

    When ``require_approval_for_l1`` is False, L1 tools execute immediately
    (Step 3 compatibility). L2 always requires approval.
    """

    require_approval_for_l1: bool = True
    require_approval_for_l2: bool = True

    @classmethod
    def disabled(cls) -> ApprovalPolicy:
        """No approval gating (Step 3 behavior)."""
        return cls(require_approval_for_l1=False, require_approval_for_l2=False)


def needs_approval(policy: ApprovalPolicy, permission: Permission) -> bool:
    if permission == Permission.L0:
        return False
    if permission == Permission.L1:
        return policy.require_approval_for_l1
    if permission == Permission.L2:
        return policy.require_approval_for_l2
    # Unknown level: fail closed -> require approval.
    return True


def risk_level(permission: Permission) -> str:
    return permission.value


def permission_of(registry: ToolRegistry, tool_name: str) -> Permission | None:
    tool = registry.get(tool_name)
    return tool.permission if tool else None
