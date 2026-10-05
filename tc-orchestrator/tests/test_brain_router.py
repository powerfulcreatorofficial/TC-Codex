from tc_orchestrator.brain import BrainResponse, MockBrain
from tc_orchestrator.brain_router import BrainBudget, BrainPricing, BrainRouter, BrainRouterConfig
from tc_orchestrator.models import ChatMessage


def _messages_failed_twice():
    return [
        ChatMessage(role="user", content="fix it"),
        ChatMessage(role="tool", name="exec_command", content="ok=False | error=boom"),
        ChatMessage(role="tool", name="read_file", content="ok=False | error=boom"),
    ]


def test_primary_used_for_normal_work():
    primary = MockBrain([(None, "done", "stop")])
    higher = MockBrain([(None, "higher", "stop")])
    router = BrainRouter(primary, higher, BrainRouterConfig(higher_enabled=True))

    response = router.chat([ChatMessage(role="user", content="hello")], [])

    assert response.content == "done"
    assert router.route == "primary"
    assert router.calls[0].route == "primary"


def test_escalates_after_observed_tool_failures():
    primary = MockBrain([(None, "primary", "stop")])
    higher = MockBrain([(None, "higher", "stop")])
    router = BrainRouter(primary, higher, BrainRouterConfig(higher_enabled=True))

    response = router.chat(_messages_failed_twice(), [])

    assert response.content == "higher"
    assert router.calls[-1].route == "higher"
    assert "tool failures" in router.calls[-1].reason


def test_budget_blocks_higher_brain():
    primary = MockBrain([(None, "primary", "stop")])
    higher = MockBrain([(None, "higher", "stop")])
    router = BrainRouter(
        primary,
        higher,
        BrainRouterConfig(
            higher_enabled=True,
            budget=BrainBudget(max_usd=0.0, max_higher_calls=1),
        ),
    )

    response = router.chat(_messages_failed_twice(), [])

    assert response.content == "primary"
    assert router.calls[-1].route == "primary"
    assert router.calls[-1].reason == "higher brain budget exhausted"


def test_usage_and_cost_are_normalized():
    class UsageBrain:
        def chat(self, messages, tools):
            return BrainResponse(
                content="ok",
                tool_calls=[],
                finish_reason="stop",
                raw={"usage": {"prompt_tokens": 1000, "completion_tokens": 500}},
            )

    router = BrainRouter(
        UsageBrain(),
        None,
        BrainRouterConfig(primary_pricing=BrainPricing(0.80, 4.0)),
    )
    router.chat([ChatMessage(role="user", content="hi")], [])

    assert router.calls[0].input_tokens == 1000
    assert router.calls[0].output_tokens == 500
    assert router.calls[0].total_tokens == 1500
    assert abs(router.calls[0].estimated_cost_usd - 0.0028) < 1e-9
