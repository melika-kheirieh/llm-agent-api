from dataclasses import dataclass

from app.agent.context import TrustedScope
from app.agent.contracts import AgentAction
from app.agent.state import AgentStatus
from app.agent.tools import ToolResult
from app.evaluation.agent_cases import (
    DIRECT_SUCCESS_EVENTS,
    MODEL_FAILURE_EVENTS,
    ROUTE_PARSE_FAILURE_EVENTS,
    TOOL_SUCCESS_EVENTS,
    EvaluationCase,
)
from app.evaluation.metrics import (
    EvaluationResult,
    RoutingAccuracy,
    routing_accuracy,
    routing_agreement,
)
from app.evaluation.runner import run_case
from app.evaluation.trajectory import Trajectory
from app.infra.config import ROUTER_MODE_KEYWORD, ROUTER_MODE_LLM
from app.infra.errors import FailureClass
from app.tools.catalog import DEFAULT_SCOPE


@dataclass(frozen=True)
class RoutingScenario:
    """One user message evaluated under keyword and LLM routers."""

    name: str
    message: str
    keyword_expected: Trajectory
    llm_route_output: str
    llm_expected: Trajectory
    tool_results: tuple[ToolResult, ...] | None = None
    trusted_scope: TrustedScope | None = None

    def keyword_case(self) -> EvaluationCase:
        return EvaluationCase(
            name=f"{self.name}__keyword",
            message=self.message,
            expected=self.keyword_expected,
            tool_results=self.tool_results,
            router_kind=ROUTER_MODE_KEYWORD,
            trusted_scope=self.trusted_scope,
        )

    def llm_case(self) -> EvaluationCase:
        return EvaluationCase(
            name=f"{self.name}__llm",
            message=self.message,
            expected=self.llm_expected,
            tool_results=self.tool_results,
            router_kind=ROUTER_MODE_LLM,
            route_output=self.llm_route_output,
            trusted_scope=self.trusted_scope,
        )


@dataclass(frozen=True)
class StrategyReport:
    router_type: str
    results: tuple[EvaluationResult, ...]
    accuracy: RoutingAccuracy


@dataclass(frozen=True)
class RoutingComparison:
    keyword: StrategyReport
    llm: StrategyReport
    agreement: RoutingAccuracy


_DIRECT_SUCCESS = Trajectory(
    action=AgentAction.DIRECT.value,
    tool_name=None,
    tool_arguments=None,
    verification_result=None,
    failure_class=None,
    attempts=0,
    recovery_decision=None,
    outcome="success",
    terminal_status=AgentStatus.COMPLETED.value,
    event_names=DIRECT_SUCCESS_EVENTS,
)
_WORK_ORDER_SUCCESS = Trajectory(
    action=AgentAction.USE_TOOL.value,
    tool_name="work_order_lookup",
    tool_arguments={"work_order_id": "WO-123"},
    verification_result=True,
    failure_class=None,
    attempts=1,
    recovery_decision=None,
    outcome="success",
    terminal_status=AgentStatus.COMPLETED.value,
    event_names=TOOL_SUCCESS_EVENTS,
)

ROUTING_COMPARISON_CASES = (
    RoutingScenario(
        name="agreement_direct",
        message="hello there",
        keyword_expected=_DIRECT_SUCCESS,
        llm_route_output='{"action": "direct", "tool_name": null, "arguments": null}',
        llm_expected=_DIRECT_SUCCESS,
    ),
    RoutingScenario(
        name="agreement_work_order",
        message="Check work order WO-123",
        trusted_scope=DEFAULT_SCOPE,
        keyword_expected=_WORK_ORDER_SUCCESS,
        llm_route_output=(
            '{"action": "use_tool", "tool_name": "work_order_lookup", '
            '"arguments": {"work_order_id": "WO-123"}}'
        ),
        llm_expected=_WORK_ORDER_SUCCESS,
    ),
    RoutingScenario(
        name="disagreement_llm_skips_tool",
        message="Check work order WO-123",
        trusted_scope=DEFAULT_SCOPE,
        keyword_expected=_WORK_ORDER_SUCCESS,
        llm_route_output='{"action": "direct", "tool_name": null, "arguments": null}',
        llm_expected=_DIRECT_SUCCESS,
    ),
    RoutingScenario(
        name="llm_invalid_tool",
        message="hello there",
        keyword_expected=_DIRECT_SUCCESS,
        llm_route_output=(
            '{"action": "use_tool", "tool_name": "billing_lookup", "arguments": {}}'
        ),
        llm_expected=Trajectory(
            action=AgentAction.USE_TOOL.value,
            tool_name="billing_lookup",
            tool_arguments={},
            verification_result=None,
            failure_class=FailureClass.MODEL_ERROR.value,
            attempts=0,
            recovery_decision=None,
            outcome="failure",
            terminal_status=AgentStatus.FAILED.value,
            event_names=MODEL_FAILURE_EVENTS,
        ),
    ),
    RoutingScenario(
        name="llm_invalid_arguments",
        message="Check work order WO-123",
        trusted_scope=DEFAULT_SCOPE,
        keyword_expected=_WORK_ORDER_SUCCESS,
        llm_route_output=(
            '{"action": "use_tool", "tool_name": "work_order_lookup", '
            '"arguments": {"work_order_id": 123}}'
        ),
        llm_expected=Trajectory(
            action=AgentAction.USE_TOOL.value,
            tool_name="work_order_lookup",
            tool_arguments={"work_order_id": 123},
            verification_result=None,
            failure_class=FailureClass.MODEL_ERROR.value,
            attempts=0,
            recovery_decision=None,
            outcome="failure",
            terminal_status=AgentStatus.FAILED.value,
            event_names=MODEL_FAILURE_EVENTS,
        ),
    ),
    RoutingScenario(
        name="llm_malformed_output",
        message="hello there",
        keyword_expected=_DIRECT_SUCCESS,
        llm_route_output="not a routing object",
        llm_expected=Trajectory(
            action=None,
            tool_name=None,
            tool_arguments=None,
            verification_result=None,
            failure_class=FailureClass.MODEL_ERROR.value,
            attempts=0,
            recovery_decision=None,
            outcome="failure",
            terminal_status=AgentStatus.FAILED.value,
            event_names=ROUTE_PARSE_FAILURE_EVENTS,
        ),
    ),
)


async def run_routing_comparison(
    scenarios: tuple[RoutingScenario, ...] = ROUTING_COMPARISON_CASES,
) -> RoutingComparison:
    """Run the same messages through keyword and LLM routers. Does not score answer text."""
    keyword_results = []
    llm_results = []
    for scenario in scenarios:
        keyword_results.append(await run_case(scenario.keyword_case()))
        llm_results.append(await run_case(scenario.llm_case()))
    keyword = tuple(keyword_results)
    llm = tuple(llm_results)
    return RoutingComparison(
        keyword=StrategyReport(
            router_type=ROUTER_MODE_KEYWORD,
            results=keyword,
            accuracy=routing_accuracy(keyword),
        ),
        llm=StrategyReport(
            router_type=ROUTER_MODE_LLM,
            results=llm,
            accuracy=routing_accuracy(llm),
        ),
        agreement=routing_agreement(keyword, llm),
    )
