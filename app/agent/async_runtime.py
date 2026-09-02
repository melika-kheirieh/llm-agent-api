import asyncio
from dataclasses import replace

from app.agent.contracts import AgentAction, AgentDecision, AgentRequest
from app.agent.router import AgentRouter
from app.agent.schemas import Analysis
from app.agent.state import AgentState, AgentStatus
from app.agent.tools import AgentTool, ToolResult
from app.agent.verification import ToolVerifier
from app.infra.errors import UpstreamLLMError
from app.llm.async_base import AsyncLLMClient

_REVIEW_RESPONSE = "The request could not be verified."


class AsyncAgentRuntime:
    """Async execution boundary for the chat agent pipeline."""

    def __init__(
        self,
        llm: AsyncLLMClient,
        timeout_seconds: float = 60.0,
        router: AgentRouter | None = None,
        tools: dict[str, AgentTool] | None = None,
        verifier: ToolVerifier | None = None,
    ):
        self.llm = llm
        self.timeout_seconds = timeout_seconds
        self.router = router or AgentRouter()
        self.tools = tools or {}
        self.verifier = verifier or ToolVerifier()

    def analyze(self, message: str) -> Analysis:
        return Analysis(language="auto", tone="neutral", task_type="qa")

    async def respond(self, message: str, analysis: Analysis) -> str:
        prompt = f"Answer clearly.\n\nUser: {message}"
        return (await self.llm.generate(prompt)).strip()

    async def run(self, message: str) -> str:
        try:
            async with asyncio.timeout(self.timeout_seconds):
                return await self._execute(message)
        except TimeoutError as e:
            raise UpstreamLLMError("LLM request timed out") from e

    async def _execute(self, message: str) -> str:
        request = AgentRequest(message=message, metadata={})
        state = AgentState(request=request, status=AgentStatus.RUNNING)
        decision = self.router.route(request)
        state = replace(state, decision=decision)

        if decision.action == AgentAction.DIRECT:
            analysis = self.analyze(message)
            return await self.respond(message, analysis)

        if decision.action == AgentAction.USE_TOOL:
            return await self._run_tool(state, decision)

        return _REVIEW_RESPONSE

    async def _run_tool(self, state: AgentState, decision: AgentDecision) -> str:
        tool = self.tools.get(decision.tool_name or "")
        if tool is None:
            return _REVIEW_RESPONSE

        result = await tool.execute(decision.arguments or {})
        verified = self.verifier.verify(result)
        state = replace(
            state,
            tool_result=result,
            verification_result=verified,
            status=(
                AgentStatus.COMPLETED if verified else AgentStatus.NEEDS_HUMAN_REVIEW
            ),
        )
        if state.status == AgentStatus.NEEDS_HUMAN_REVIEW:
            return _REVIEW_RESPONSE
        return _format_tool_answer(result)

    async def aclose(self) -> None:
        aclose = getattr(self.llm, "aclose", None)
        if aclose is not None:
            await aclose()


def _format_tool_answer(result: ToolResult) -> str:
    data = result.data
    work_order_id = data.get("work_order_id")
    status = data.get("status")
    issue_type = data.get("issue_type")
    if work_order_id and status:
        issue = f" ({issue_type})" if issue_type else ""
        return f"Work order {work_order_id} is {status}{issue}."
    return "Tool execution completed."
