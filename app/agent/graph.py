"""LangGraph transition layer for AsyncAgentRuntime.

Nodes wrap existing runtime steps. Routing, tools, verification, recovery,
and answer generation stay in those components. This module does not add
multi-agent, RAG, or checkpointed memory.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

from langgraph.graph import END, START, StateGraph

from app.agent.context import RequestContext
from app.agent.contracts import AgentAction
from app.agent.recovery import RecoveryAction
from app.agent.state import AgentState, AgentStatus
from app.infra.errors import AgentFailure, FailureClass

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

    from app.agent.async_runtime import AsyncAgentRuntime


class GraphState(TypedDict):
    """Envelope around AgentState. Not a second domain model."""

    agent: AgentState
    request_ctx: RequestContext
    response: str | None
    pending_error: AgentFailure | None
    attempt_class: FailureClass | None


def _after_route(state: GraphState) -> str:
    if state.get("pending_error") is not None:
        return "end"
    agent = state["agent"]
    if agent.status in (AgentStatus.FAILED, AgentStatus.NEEDS_HUMAN_REVIEW):
        return "end"
    decision = agent.decision
    if decision is None:
        return "end"
    if decision.action == AgentAction.DIRECT:
        return "answer_node"
    if decision.action == AgentAction.USE_TOOL:
        return "tool_node"
    return "end"


def _after_tool(state: GraphState) -> str:
    if state["agent"].status == AgentStatus.NEEDS_HUMAN_REVIEW:
        return "end"
    return "verify_node"


def _after_verify(state: GraphState) -> str:
    if state["agent"].verification_result:
        return "answer_node"
    return "recovery_node"


def _after_recovery(state: GraphState) -> str:
    if state["agent"].recovery_decision == RecoveryAction.RETRY:
        return "tool_node"
    return "end"


def build_agent_graph(runtime: AsyncAgentRuntime) -> StateGraph:
    """Wire START → route → (answer | tool → verify → (answer | recovery))."""

    async def route_node(state: GraphState) -> dict:
        agent, pending, response = await runtime._route_step(state["agent"])
        update: dict = {"agent": agent, "pending_error": pending}
        if response is not None:
            update["response"] = response
        return update

    async def tool_node(state: GraphState) -> dict:
        agent, attempt_class, response = await runtime._tool_step(state["agent"])
        update: dict = {"agent": agent, "attempt_class": attempt_class}
        if response is not None:
            update["response"] = response
        return update

    def verify_node(state: GraphState) -> dict:
        agent = runtime._verify_step(
            state["agent"],
            state["request_ctx"],
            state.get("attempt_class"),
        )
        return {"agent": agent}

    def recovery_node(state: GraphState) -> dict:
        agent, response = runtime._recovery_step(state["agent"])
        update: dict = {"agent": agent}
        if response is not None:
            update["response"] = response
        return update

    async def answer_node(state: GraphState) -> dict:
        agent, response, pending = await runtime._answer_step(state["agent"])
        update: dict = {"agent": agent, "pending_error": pending}
        if response is not None:
            update["response"] = response
        return update

    graph = StateGraph(GraphState)
    graph.add_node("route_node", route_node)
    graph.add_node("tool_node", tool_node)
    graph.add_node("verify_node", verify_node)
    graph.add_node("recovery_node", recovery_node)
    graph.add_node("answer_node", answer_node)
    graph.add_edge(START, "route_node")
    graph.add_conditional_edges(
        "route_node",
        _after_route,
        {"answer_node": "answer_node", "tool_node": "tool_node", "end": END},
    )
    graph.add_conditional_edges(
        "tool_node",
        _after_tool,
        {"verify_node": "verify_node", "end": END},
    )
    graph.add_conditional_edges(
        "verify_node",
        _after_verify,
        {"answer_node": "answer_node", "recovery_node": "recovery_node"},
    )
    graph.add_conditional_edges(
        "recovery_node",
        _after_recovery,
        {"tool_node": "tool_node", "end": END},
    )
    graph.add_edge("answer_node", END)
    return graph


def compile_agent_graph(runtime: AsyncAgentRuntime) -> CompiledStateGraph:
    return build_agent_graph(runtime).compile()
