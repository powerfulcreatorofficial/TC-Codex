"""Hard, pre-checked task budgets.

Every expensive operation (model call, tool call, repair attempt) must call
``charge_*`` BEFORE performing the operation. ``BudgetExceeded`` is raised at
charge time, never discovered by post-hoc accounting.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


class BudgetExceeded(Exception):
    """Raised when a charge would exceed a hard task budget."""

    def __init__(self, dimension: str, limit: float, attempted: float) -> None:
        self.dimension = dimension
        self.limit = limit
        self.attempted = attempted
        super().__init__(
            f"budget exceeded: {dimension} (limit={limit}, attempted={attempted})"
        )


@dataclass
class TaskBudget:
    """Bounded budget for a single engineering task.

    All limits are hard. ``charge_*`` methods check BEFORE consuming and
    raise :class:`BudgetExceeded` when a charge would cross a limit.
    """

    max_steps: int = 30
    max_model_calls: int = 12
    max_tool_calls: int = 60
    max_repair_attempts: int = 3
    max_wall_seconds: float = 900.0
    max_cost_usd: float = 2.0

    steps_used: int = 0
    model_calls_used: int = 0
    tool_calls_used: int = 0
    repair_attempts_used: int = 0
    cost_usd_used: float = 0.0
    started_at: float = field(default_factory=time.monotonic)

    # ---- time ----

    def seconds_remaining(self) -> float:
        return self.max_wall_seconds - (time.monotonic() - self.started_at)

    def check_time(self) -> None:
        if self.seconds_remaining() <= 0:
            raise BudgetExceeded(
                "wall_seconds", self.max_wall_seconds, time.monotonic() - self.started_at
            )

    # ---- counters (check-then-consume) ----

    def charge_step(self) -> None:
        self.check_time()
        if self.steps_used + 1 > self.max_steps:
            raise BudgetExceeded("steps", self.max_steps, self.steps_used + 1)
        self.steps_used += 1

    def charge_model_call(self, estimated_cost_usd: float = 0.0) -> None:
        """Must be called BEFORE issuing a model call."""
        self.check_time()
        if self.model_calls_used + 1 > self.max_model_calls:
            raise BudgetExceeded("model_calls", self.max_model_calls, self.model_calls_used + 1)
        if self.cost_usd_used + estimated_cost_usd > self.max_cost_usd:
            raise BudgetExceeded(
                "cost_usd", self.max_cost_usd, self.cost_usd_used + estimated_cost_usd
            )
        self.model_calls_used += 1
        self.cost_usd_used += estimated_cost_usd

    def record_actual_cost(self, delta_usd: float) -> None:
        """Record true cost after a call (supplement, not a substitute, for
        the pre-check)."""
        if delta_usd > 0:
            self.cost_usd_used += delta_usd

    def charge_tool_call(self) -> None:
        self.check_time()
        if self.tool_calls_used + 1 > self.max_tool_calls:
            raise BudgetExceeded("tool_calls", self.max_tool_calls, self.tool_calls_used + 1)
        self.tool_calls_used += 1

    def charge_repair_attempt(self) -> None:
        self.check_time()
        if self.repair_attempts_used + 1 > self.max_repair_attempts:
            raise BudgetExceeded(
                "repair_attempts", self.max_repair_attempts, self.repair_attempts_used + 1
            )
        self.repair_attempts_used += 1

    # ---- reporting ----

    def usage(self) -> dict[str, float | int]:
        return {
            "steps_used": self.steps_used,
            "model_calls_used": self.model_calls_used,
            "tool_calls_used": self.tool_calls_used,
            "repair_attempts_used": self.repair_attempts_used,
            "cost_usd_used": round(self.cost_usd_used, 6),
            "wall_seconds_used": round(time.monotonic() - self.started_at, 3),
        }
