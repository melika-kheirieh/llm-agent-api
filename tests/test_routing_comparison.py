import asyncio

from app.evaluation.metrics import routing_accuracy, routing_agreement, score_routing
from app.evaluation.routing_comparison import (
    ROUTING_COMPARISON_CASES,
    run_routing_comparison,
)
from app.evaluation.trajectory import Trajectory
from app.infra.config import ROUTER_MODE_KEYWORD, ROUTER_MODE_LLM


def test_routing_comparison_runs_keyword_and_llm_strategies():
    comparison = asyncio.run(run_routing_comparison())

    assert comparison.keyword.router_type == ROUTER_MODE_KEYWORD
    assert comparison.llm.router_type == ROUTER_MODE_LLM
    assert comparison.keyword.accuracy.case_count == len(ROUTING_COMPARISON_CASES)
    assert comparison.llm.accuracy.case_count == len(ROUTING_COMPARISON_CASES)
    assert all(result.passed for result in comparison.keyword.results)
    assert all(result.passed for result in comparison.llm.results)
    assert comparison.keyword.accuracy.action_accuracy == 1.0
    assert comparison.keyword.accuracy.tool_accuracy == 1.0
    assert comparison.keyword.accuracy.argument_accuracy == 1.0
    assert comparison.keyword.accuracy.failure_accuracy == 1.0
    assert comparison.llm.accuracy.action_accuracy == 1.0
    assert comparison.llm.accuracy.tool_accuracy == 1.0
    assert comparison.llm.accuracy.argument_accuracy == 1.0
    assert comparison.llm.accuracy.failure_accuracy == 1.0


def test_routing_comparison_measures_strategy_disagreement():
    comparison = asyncio.run(run_routing_comparison())

    assert comparison.agreement.case_count == len(ROUTING_COMPARISON_CASES)
    assert comparison.agreement.action_accuracy < 1.0
    assert comparison.agreement.failure_accuracy < 1.0


def test_routing_score_ignores_answer_text():
    expected = Trajectory(action="direct", tool_name=None, failure_class=None)
    actual = Trajectory(action="direct", tool_name=None, failure_class=None)
    score = score_routing(expected, actual)

    assert score.action_match is True
    assert score.tool_match is True
    assert score.arguments_match is True
    assert score.failure_match is True
    assert "response_text" not in Trajectory.__dataclass_fields__


def test_routing_agreement_compares_actuals_not_answers():
    left = routing_accuracy([])
    assert left.case_count == 0
    agreement = routing_agreement([], [])
    assert agreement.case_count == 0
