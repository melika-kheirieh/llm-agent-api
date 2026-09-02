import re
from typing import Protocol

from app.agent.contracts import AgentAction, AgentDecision, AgentRequest
from app.tools.maintenance_policy import ALLOWED_ISSUE_TYPES

_WORK_ORDER_ID = re.compile(r"\bWO-?\d+\b", re.IGNORECASE)
_WORK_ORDER_NUMERIC = re.compile(r"work order\s+(\d+)", re.IGNORECASE)


def extract_work_order_id(message: str) -> str | None:
    match = _WORK_ORDER_ID.search(message)
    if match:
        raw = match.group(0).upper()
        if raw.startswith("WO") and not raw.startswith("WO-"):
            return f"WO-{raw[2:]}"
        return raw

    match = _WORK_ORDER_NUMERIC.search(message)
    if match:
        return match.group(1)
    return None


def extract_issue_type(message: str) -> str | None:
    lower = message.lower()
    for issue in sorted(ALLOWED_ISSUE_TYPES, key=len, reverse=True):
        if issue in lower:
            return issue
    return None


class Router(Protocol):
    """Routing boundary used by AsyncAgentRuntime."""

    router_type: str

    async def route(self, request: AgentRequest) -> AgentDecision: ...


class AgentRouter:
    """Deterministic keyword router. Default production and evaluation path."""

    router_type = "keyword"

    async def route(self, request: AgentRequest) -> AgentDecision:
        return self.decide(request)

    def decide(self, request: AgentRequest) -> AgentDecision:
        message = request.message.lower()

        if "policy" in message:
            issue_type = extract_issue_type(request.message)
            arguments = {"issue_type": issue_type} if issue_type else {}
            return AgentDecision(
                action=AgentAction.USE_TOOL,
                tool_name="maintenance_policy_lookup",
                arguments=arguments,
            )

        if "work order" in message or "maintenance" in message:
            work_order_id = extract_work_order_id(request.message)
            arguments = {"work_order_id": work_order_id} if work_order_id else {}
            return AgentDecision(
                action=AgentAction.USE_TOOL,
                tool_name="work_order_lookup",
                arguments=arguments,
            )

        return AgentDecision(action=AgentAction.DIRECT)
