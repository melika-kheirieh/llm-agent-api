import re
from typing import Protocol

from app.agent.contracts import AgentAction, AgentDecision, AgentRequest

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


class Router(Protocol):
    """Routing boundary used by AsyncAgentRuntime."""

    async def route(self, request: AgentRequest) -> AgentDecision: ...


class AgentRouter:
    """Deterministic keyword router. Default production and evaluation path."""

    async def route(self, request: AgentRequest) -> AgentDecision:
        return self.decide(request)

    def decide(self, request: AgentRequest) -> AgentDecision:
        message = request.message.lower()

        if "work order" in message or "maintenance" in message:
            work_order_id = extract_work_order_id(request.message)
            arguments = {"work_order_id": work_order_id} if work_order_id else {}
            return AgentDecision(
                action=AgentAction.USE_TOOL,
                tool_name="work_order_lookup",
                arguments=arguments,
            )

        return AgentDecision(action=AgentAction.DIRECT)
