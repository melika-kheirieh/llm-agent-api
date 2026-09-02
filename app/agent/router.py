from app.agent.contracts import AgentAction, AgentDecision, AgentRequest


class AgentRouter:
    """Small deterministic router used as the first agent boundary."""

    def route(self, request: AgentRequest) -> AgentDecision:
        message = request.message.lower()

        if "work order" in message or "maintenance" in message:
            return AgentDecision(
                action=AgentAction.USE_TOOL,
                tool_name="work_order_lookup",
                arguments={"query": request.message},
            )

        return AgentDecision(action=AgentAction.DIRECT)
