from app.agent.context import (
    ContextPolicy,
    HistoryTurn,
    RequestContext,
    TrustedScope,
    truncate_history,
)
from app.agent.observation import Observation
from app.tools.work_order import WorkOrderResult


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
        data=WorkOrderResult(
            work_order_id="WO-123",
            status="open",
            issue_type="plumbing",
        ).as_data(),
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
    assert context.answer.evidence[0].data["tenant_id"] == "forged"
    assert context.trusted_scope.tenant_id != context.answer.evidence[0].data["tenant_id"]
