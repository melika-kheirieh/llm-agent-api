import asyncio
import json
from typing import Any

from pydantic import ValidationError

from app.agent.contracts import AgentAction, AgentDecision, AgentRequest
from app.agent.schemas import RoutingOutput
from app.infra.errors import AgentFailure, ModelError, ModelTimeout, RoutingError
from app.llm.async_base import AsyncLLMClient
from app.tools.work_order import WorkOrderLookupRequest

ALLOWED_ROUTE_TOOLS = frozenset({"work_order_lookup"})
ROUTING_PROMPT_MARKER = "Respond with a JSON routing decision only."


def build_routing_prompt(message: str, allowed_tools: frozenset[str]) -> str:
    tools = ", ".join(sorted(allowed_tools)) or "(none)"
    return (
        f"{ROUTING_PROMPT_MARKER}\n"
        'Schema: {"action": "direct" | "use_tool", "tool_name": string | null, '
        '"arguments": object | null}\n'
        f"Allowed tools: {tools}\n"
        "Rules:\n"
        "- action=direct: tool_name and arguments must be null\n"
        "- action=use_tool: tool_name must be an allowed tool; "
        "arguments must match that tool\n"
        f"User: {message}\n"
    )


def parse_routing_decision(
    text: str,
    allowed_tools: frozenset[str] | None = None,
) -> AgentDecision:
    allowed = allowed_tools if allowed_tools is not None else ALLOWED_ROUTE_TOOLS
    try:
        payload = json.loads(_extract_json_object(text))
        parsed = RoutingOutput.model_validate(payload)
    except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as e:
        raise RoutingError("Malformed routing output") from e

    if parsed.action == AgentAction.DIRECT:
        if parsed.tool_name is not None or (
            parsed.arguments is not None and parsed.arguments != {}
        ):
            raise RoutingError("Malformed routing output")
        return AgentDecision(action=AgentAction.DIRECT)

    if parsed.tool_name is None or parsed.tool_name not in allowed:
        raise RoutingError(
            "Invalid tool selection",
            decision=AgentDecision(
                action=AgentAction.USE_TOOL,
                tool_name=parsed.tool_name,
                arguments=parsed.arguments if parsed.arguments is not None else {},
            ),
        )

    return AgentDecision(
        action=AgentAction.USE_TOOL,
        tool_name=parsed.tool_name,
        arguments=_validate_tool_arguments(parsed.tool_name, parsed.arguments),
    )


def _extract_json_object(text: str) -> str:
    stripped = text.strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("routing output is not a JSON object")
    return stripped[start : end + 1]


def _validate_tool_arguments(
    tool_name: str,
    arguments: dict[str, Any] | None,
) -> dict[str, Any]:
    raw = arguments if arguments is not None else {}
    if tool_name == "work_order_lookup":
        return _validate_work_order_arguments(raw)
    raise RoutingError(
        "Invalid tool selection",
        decision=AgentDecision(
            action=AgentAction.USE_TOOL,
            tool_name=tool_name,
            arguments=raw,
        ),
    )


def _validate_work_order_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    decision = AgentDecision(
        action=AgentAction.USE_TOOL,
        tool_name="work_order_lookup",
        arguments=arguments,
    )
    extra = set(arguments) - {"work_order_id"}
    if extra:
        raise RoutingError("Invalid routing arguments", decision=decision)
    if "work_order_id" in arguments:
        value = arguments["work_order_id"]
        if not isinstance(value, str) or not value.strip():
            raise RoutingError("Invalid routing arguments", decision=decision)
        typed = WorkOrderLookupRequest.from_arguments(arguments)
        if typed.work_order_id is None:
            raise RoutingError("Invalid routing arguments", decision=decision)
        return {"work_order_id": typed.work_order_id}
    return {}


class LlmAgentRouter:
    """LLM-backed router. Requests JSON and validates it before returning a decision."""

    router_type = "llm"

    def __init__(
        self,
        llm: AsyncLLMClient,
        allowed_tools: frozenset[str] | None = None,
        timeout_seconds: float = 60.0,
    ):
        self.llm = llm
        self.allowed_tools = (
            allowed_tools if allowed_tools is not None else ALLOWED_ROUTE_TOOLS
        )
        self.timeout_seconds = timeout_seconds

    async def route(self, request: AgentRequest) -> AgentDecision:
        prompt = build_routing_prompt(request.message, self.allowed_tools)
        try:
            async with asyncio.timeout(self.timeout_seconds):
                raw = await self.llm.generate(prompt)
        except asyncio.CancelledError:
            raise
        except TimeoutError as e:
            raise ModelTimeout("Model request timed out") from e
        except AgentFailure:
            raise
        except Exception as e:
            raise ModelError(str(e)) from e
        return parse_routing_decision(raw, self.allowed_tools)
