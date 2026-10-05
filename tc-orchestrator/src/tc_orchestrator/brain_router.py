"""Multi-brain routing, cost control, and provider resilience for TC.

The router keeps the provider-independent Brain protocol intact while adding:
- a primary model for normal engineering work;
- an optional higher brain for difficult work;
- deterministic escalation signals derived only from observable transcript data;
- a per-task estimated cost budget;
- bounded provider failover.

It intentionally never executes tools and never receives owner secrets.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .brain import Brain, BrainResponse
from .models import ChatMessage


@dataclass(frozen=True)
class BrainPricing:
    input_usd_per_mtok: float = 0.0
    output_usd_per_mtok: float = 0.0


@dataclass(frozen=True)
class BrainBudget:
    max_usd: float = 0.50
    max_higher_calls: int = 3


@dataclass
class BrainCall:
    route: str
    model: str
    reason: str
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    fallback: bool = False

    def metadata(self) -> dict[str, Any]:
        return {
            "route": self.route,
            "model": self.model,
            "reason": self.reason,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "estimated_cost_usd": round(self.estimated_cost_usd, 8),
            "fallback": self.fallback,
        }


@dataclass
class BrainRouterConfig:
    primary_model: str = "qwen/qwen3.8-27b"
    higher_model: str = "gpt-6-astra"
    higher_enabled: bool = False
    escalation_failures: int = 2
    escalation_repetition: int = 2
    budget: BrainBudget = field(default_factory=BrainBudget)
    primary_pricing: BrainPricing = field(default_factory=BrainPricing)
    higher_pricing: BrainPricing = field(default_factory=lambda: BrainPricing(10.0, 50.0))

    @property
    def max_higher_calls(self) -> int:
        return self.budget.max_higher_calls


class BrainRouter:
    """Stateful per-task router around two Brain implementations."""

    def __init__(self, primary: Brain, higher: Brain | None, config: BrainRouterConfig):
        self._primary = primary
        self._higher = higher
        self._config = config
        self._route = "primary"
        self._higher_calls = 0
        self._estimated_cost = 0.0
        self._higher_estimated_cost = 0.0
        self._failures_seen = 0
        self.calls: list[BrainCall] = []

    @property
    def route(self) -> str:
        return self._route

    @property
    def estimated_cost_usd(self) -> float:
        return self._estimated_cost

    @property
    def higher_estimated_cost_usd(self) -> float:
        return self._higher_estimated_cost

    def chat(self, messages: list[ChatMessage], tools: list[dict[str, Any]]) -> BrainResponse:
        route, reason = self._choose_route(messages)
        brain = self._higher if route == "higher" and self._higher is not None else self._primary
        model = self._config.higher_model if route == "higher" else self._config.primary_model
        fallback = False
        try:
            response = brain.chat(messages, tools)
        except Exception:
            if route == "primary" and self._higher_available() and self._within_higher_budget():
                self._route = "higher"
                route = "higher"
                reason = "primary provider failure"
                model = self._config.higher_model
                self._higher_calls += 1
                fallback = True
                response = self._higher.chat(messages, tools)  # type: ignore[union-attr]
            else:
                raise

        call = self._make_call(route, model, reason, response, fallback=fallback)
        self.calls.append(call)
        self._estimated_cost += call.estimated_cost_usd
        if call.route == "higher":
            self._higher_estimated_cost += call.estimated_cost_usd
        self._observe_response(response)
        return response

    def _choose_route(self, messages: list[ChatMessage]) -> tuple[str, str]:
        if self._route == "higher":
            return "higher", "already escalated for this task"
        if not self._higher_available():
            return "primary", "higher brain unavailable"
        if not self._within_higher_budget():
            return "primary", "higher brain budget exhausted"

        failed_tools = 0
        recent_signatures: list[str] = []
        for message in messages[-10:]:
            if message.role == "tool" and message.content and "ok=False" in message.content:
                failed_tools += 1
            if message.role == "assistant" and message.tool_calls:
                for call in message.tool_calls:
                    try:
                        recent_signatures.append(
                            f"{call.get('function', {}).get('name','')}:{call.get('function', {}).get('arguments','')}"
                        )
                    except AttributeError:
                        pass
        repeated = 0
        if recent_signatures:
            repeated = max(recent_signatures.count(x) for x in set(recent_signatures))

        if failed_tools >= self._config.escalation_failures:
            self._route = "higher"
            self._higher_calls += 1
            return "higher", f"{failed_tools} observed tool failures"
        if repeated >= self._config.escalation_repetition:
            self._route = "higher"
            self._higher_calls += 1
            return "higher", f"repeated tool action observed {repeated} times"
        if self._failures_seen >= self._config.escalation_failures:
            self._route = "higher"
            self._higher_calls += 1
            return "higher", f"{self._failures_seen} provider/response failures observed"
        return "primary", "normal task routing"

    def _observe_response(self, response: BrainResponse) -> None:
        if response.finish_reason in {"error", "failed"}:
            self._failures_seen += 1

    def _higher_available(self) -> bool:
        return self._config.higher_enabled and self._higher is not None and self._config.max_higher_calls > 0

    def _within_higher_budget(self) -> bool:
        return self._higher_calls < self._config.budget.max_higher_calls and self._higher_estimated_cost < self._config.budget.max_usd

    def _make_call(
        self,
        route: str,
        model: str,
        reason: str,
        response: BrainResponse,
        *,
        fallback: bool,
    ) -> BrainCall:
        usage = response.raw.get("usage") if isinstance(response.raw, dict) else None
        usage = usage if isinstance(usage, dict) else {}
        input_tokens = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
        output_tokens = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
        total_tokens = int(usage.get("total_tokens") or (input_tokens + output_tokens))
        pricing = self._config.higher_pricing if route == "higher" else self._config.primary_pricing
        cost = (input_tokens / 1_000_000) * pricing.input_usd_per_mtok
        cost += (output_tokens / 1_000_000) * pricing.output_usd_per_mtok
        return BrainCall(
            route=route,
            model=model,
            reason=reason,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=cost,
            fallback=fallback,
        )

