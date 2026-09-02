import asyncio

from app.agent.async_runtime import AsyncAgentRuntime
from app.agent.context import TrustedScope
from app.agent.router import AgentRouter
from app.agent.verification import ToolVerifier
from app.tools.catalog import (
    DEFAULT_SCOPE,
    OTHER_TENANT_SCOPE,
    WRONG_PROPERTY_SCOPE,
    build_default_tools,
)
from app.tools.maintenance_policy import (
    MaintenancePolicyLookupTool,
    MaintenancePolicyObservation,
    MaintenancePolicyRequest,
)


class FakeLLM:
    async def generate(self, prompt: str) -> str:
        return "unused"


def _runtime() -> AsyncAgentRuntime:
    return AsyncAgentRuntime(
        FakeLLM(),
        router=AgentRouter(),
        tools=build_default_tools(),
        verifier=ToolVerifier(),
    )


def test_matching_scope_returns_work_order_without_scope_in_arguments():
    runtime = _runtime()
    answer, state = asyncio.run(
        runtime.run_detailed("Check work order WO-123", trusted_scope=DEFAULT_SCOPE)
    )

    assert answer == "Work order WO-123 is open (plumbing)."
    assert state.decision.arguments == {"work_order_id": "WO-123"}
    assert "tenant_id" not in state.decision.arguments
    assert "property_id" not in state.decision.arguments
    assert state.verification_result is True
    assert "tenant_id" not in state.context.answer.evidence[0].data
    assert "property_id" not in state.context.answer.evidence[0].data
    assert state.observations[0].data["tenant_id"] == DEFAULT_SCOPE.tenant_id


def test_cross_tenant_lookup_never_returns_foreign_payload():
    runtime = _runtime()
    _answer, state = asyncio.run(
        runtime.run_detailed("Check work order WO-999", trusted_scope=DEFAULT_SCOPE)
    )

    assert state.verification_result is False
    assert state.attempts == 1
    assert state.recovery_decision.value == "fail"
    assert state.observations[0].data == {"error": "cross_tenant"}
    assert "status" not in state.observations[0].data
    assert "issue_type" not in state.observations[0].data
    failed = next(
        event for event in state.events if event.name == "tool_failed"
    )
    assert failed.metadata["error"] == "cross_tenant"
    assert "tenant_id" not in failed.metadata


def test_wrong_property_lookup_is_non_retryable():
    runtime = _runtime()
    _answer, state = asyncio.run(
        runtime.run_detailed("Check work order WO-456", trusted_scope=DEFAULT_SCOPE)
    )

    assert state.observations[0].data == {"error": "wrong_property"}
    assert state.attempts == 1
    assert state.recovery_decision.value == "fail"


def test_missing_scope_does_not_return_work_order():
    runtime = _runtime()
    _answer, state = asyncio.run(runtime.run_detailed("Check work order WO-123"))

    assert state.observations[0].data == {"error": "missing_scope"}
    assert state.verification_result is False


def test_other_tenant_can_read_own_work_order():
    runtime = _runtime()
    answer, state = asyncio.run(
        runtime.run_detailed(
            "Check work order WO-999",
            trusted_scope=OTHER_TENANT_SCOPE,
        )
    )

    assert "WO-999" in answer
    assert state.verification_result is True


def test_wrong_property_scope_can_read_own_work_order():
    runtime = _runtime()
    answer, state = asyncio.run(
        runtime.run_detailed(
            "Check work order WO-456",
            trusted_scope=WRONG_PROPERTY_SCOPE,
        )
    )

    assert "WO-456" in answer
    assert state.verification_result is True


def test_policy_lookup_uses_issue_type_and_trusted_scope():
    runtime = _runtime()
    answer, state = asyncio.run(
        runtime.run_detailed(
            "Check maintenance policy for plumbing",
            trusted_scope=DEFAULT_SCOPE,
        )
    )

    assert answer == "plumbing policy allows dispatch_vendor (SLA 4h)."
    assert state.decision.arguments == {"issue_type": "plumbing"}
    assert state.verification_result is True


def test_stale_policy_fails_verification():
    runtime = _runtime()
    _answer, state = asyncio.run(
        runtime.run_detailed(
            "Check maintenance policy for hvac",
            trusted_scope=DEFAULT_SCOPE,
        )
    )

    assert state.observations[0].success is True
    assert state.verification_result is False
    assert state.failure_class.value == "verification_failure"


def test_missing_policy_is_non_retryable():
    runtime = _runtime()
    _answer, state = asyncio.run(
        runtime.run_detailed(
            "Check maintenance policy for roofing",
            trusted_scope=DEFAULT_SCOPE,
        )
    )

    assert state.observations[0].data == {"error": "missing_policy"}
    assert state.attempts == 1
    assert state.recovery_decision.value == "fail"


def test_policy_verifier_rejects_unknown_tool():
    from app.agent.tools import ToolResult

    result = ToolResult(success=True, data={"anything": True})
    assert (
        ToolVerifier().verify(
            result,
            {},
            tool_name="billing_lookup",
            trusted_scope=DEFAULT_SCOPE,
        )
        is False
    )


def test_policy_observation_requires_freshness_window():
    tool = MaintenancePolicyLookupTool()
    payload = asyncio.run(
        tool.execute(
            {"issue_type": "plumbing"},
            trusted_scope=DEFAULT_SCOPE,
        )
    )
    observation = MaintenancePolicyObservation.from_data(payload.data)
    request = MaintenancePolicyRequest(issue_type="plumbing")
    assert observation is not None
    assert observation.is_valid_for(request, DEFAULT_SCOPE) is True
    assert (
        observation.is_valid_for(
            request,
            TrustedScope(tenant_id="tenant-a", property_id="prop-9"),
        )
        is False
    )
