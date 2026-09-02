from app.agent.context import (
    ContextPolicy,
    HistoryTurn,
    RequestContext,
    TrustedScope,
    sanitize_evidence_data,
    truncate_history,
)
from app.agent.observation import Observation
from app.tools.catalog import scoped_work_order_data


def test_truncate_keeps_most_recent_and_renumbers():
    turns = (
        HistoryTurn(role="user", content="a", order=99),
        HistoryTurn(role="assistant", content="b", order=1),
        HistoryTurn(role="user", content="c", order=5),
        HistoryTurn(role="assistant", content="d", order=0),
    )

    kept = truncate_history(turns, 2)

    assert [turn.content for turn in kept] == ["c", "d"]
    assert [turn.order for turn in kept] == [0, 1]


def test_truncate_history_limit_zero_drops_all():
    turns = (HistoryTurn(role="user", content="a", order=0),)
    assert truncate_history(turns, 0) == ()


def test_router_context_excludes_history_and_evidence():
    policy = ContextPolicy(max_history=8)
    history = (
        HistoryTurn(role="user", content="earlier", order=0),
        HistoryTurn(role="assistant", content="reply", order=1),
    )
    observation = Observation(
        tool_name="work_order_lookup",
        success=True,
        data=scoped_work_order_data(),
    )
    context = policy.assemble(
        RequestContext(
            message="current",
            thread_id="thread-a",
            history=history,
            trusted_scope=TrustedScope(tenant_id="tenant-1"),
        ),
        observations=(observation,),
        verification_result=True,
        attempts=1,
    )

    routing = policy.for_router(context)
    answer = policy.for_answer(context)

    assert routing.message == "current"
    assert routing.trusted_scope.tenant_id == "tenant-1"
    assert not hasattr(routing, "history")
    assert answer.history[-1].content == "reply"
    assert answer.evidence[0].trusted is True
    assert "tenant_id" not in answer.evidence[0].data
    assert "property_id" not in answer.evidence[0].data
    assert context.execution.thread_id == "thread-a"
    assert context.execution.verification_result is True


def test_unverified_observation_is_not_trusted_evidence():
    policy = ContextPolicy()
    observation = Observation(
        tool_name="work_order_lookup",
        success=True,
        data={"work_order_id": "WO-123", "status": "lost", "issue_type": "plumbing"},
    )
    context = policy.assemble(
        RequestContext(message="Check work order WO-123"),
        observations=(observation,),
        verification_result=False,
    )

    assert context.answer.evidence == ()
    assert context.trusted_scope == TrustedScope()


def test_scope_is_not_taken_from_tool_payload():
    policy = ContextPolicy()
    observation = Observation(
        tool_name="work_order_lookup",
        success=True,
        data={
            "work_order_id": "WO-123",
            "status": "open",
            "issue_type": "plumbing",
            "tenant_id": "forged",
        },
    )
    context = policy.assemble(
        RequestContext(
            message="Check work order WO-123",
            trusted_scope=TrustedScope(tenant_id="backend-tenant"),
        ),
        observations=(observation,),
        verification_result=True,
    )

    assert context.trusted_scope.tenant_id == "backend-tenant"
    assert "tenant_id" not in context.routing.message
    assert "tenant_id" not in context.answer.evidence[0].data
    assert "property_id" not in context.answer.evidence[0].data
    assert context.answer.evidence[0].data["work_order_id"] == "WO-123"


def test_sanitize_evidence_data_strips_scope_keys():
    data = scoped_work_order_data()
    sanitized = sanitize_evidence_data(data)

    assert "tenant_id" in data
    assert "property_id" in data
    assert "tenant_id" not in sanitized
    assert "property_id" not in sanitized
    assert sanitized["work_order_id"] == data["work_order_id"]
    assert sanitized["status"] == data["status"]
