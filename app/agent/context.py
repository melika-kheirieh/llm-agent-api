from dataclasses import dataclass, field
from typing import Any

from app.agent.observation import Observation

DEFAULT_MAX_HISTORY = 8
_HISTORY_ROLES = frozenset({"user", "assistant"})


@dataclass(frozen=True)
class TrustedScope:
    """Backend-provided authorization scope.

    Never derived from the user message, LLM output, or raw tool payloads.
    Missing values are allowed; they do not fail the run.
    """

    tenant_id: str | None = None
    property_id: str | None = None


@dataclass(frozen=True)
class HistoryTurn:
    role: str
    content: str
    order: int


@dataclass(frozen=True)
class RequestContext:
    """Caller input for one run. History here is still untruncated."""

    message: str
    thread_id: str | None = None
    history: tuple[HistoryTurn, ...] = ()
    trusted_scope: TrustedScope = field(default_factory=TrustedScope)


@dataclass(frozen=True)
class RoutingContext:
    """Minimal slice for routing. No history and no tool evidence."""

    message: str
    trusted_scope: TrustedScope = field(default_factory=TrustedScope)


@dataclass(frozen=True)
class ToolEvidence:
    """Verified tool payload allowed to influence the answer. trusted is always True."""

    tool_name: str
    data: dict[str, Any]
    trusted: bool = True


@dataclass(frozen=True)
class AnswerContext:
    """Slice for answer generation. History is truncated. Evidence is verified only."""

    message: str
    history: tuple[HistoryTurn, ...] = ()
    evidence: tuple[ToolEvidence, ...] = ()


@dataclass(frozen=True)
class ExecutionContext:
    """Internal run metadata. Not passed to the router or the answer model."""

    thread_id: str | None = None
    attempts: int = 0
    verification_result: bool | None = None


@dataclass(frozen=True)
class AgentContext:
    request: RequestContext
    routing: RoutingContext
    answer: AnswerContext
    execution: ExecutionContext
    trusted_scope: TrustedScope


def truncate_history(
    turns: tuple[HistoryTurn, ...] | list[HistoryTurn],
    max_history: int,
) -> tuple[HistoryTurn, ...]:
    """Keep the most recent turns, preserving relative order. Re-number from 0."""
    if max_history <= 0:
        return ()
    cleaned = tuple(
        turn
        for turn in turns
        if turn.role in _HISTORY_ROLES and turn.content.strip()
    )
    kept = cleaned[-max_history:]
    return tuple(
        HistoryTurn(role=turn.role, content=turn.content, order=index)
        for index, turn in enumerate(kept)
    )


def render_answer_prompt(context: AnswerContext) -> str:
    """Build the DIRECT-path prompt. Empty history matches the previous format."""
    parts = ["Answer clearly."]
    for turn in context.history:
        label = "User" if turn.role == "user" else "Assistant"
        parts.append(f"{label}: {turn.content}")
    parts.append(f"User: {context.message}")
    return "\n\n".join(parts)


class ThreadHistoryBuffer:
    """Process-local bounded history. Not persistence and not shared across runtimes."""

    def __init__(self) -> None:
        self._turns: dict[str, tuple[HistoryTurn, ...]] = {}

    def turns(self, thread_id: str | None) -> tuple[HistoryTurn, ...]:
        if not thread_id:
            return ()
        return self._turns.get(thread_id, ())

    def record(
        self,
        thread_id: str | None,
        user_message: str,
        assistant_message: str,
        max_history: int,
    ) -> None:
        if not thread_id:
            return
        existing = self._turns.get(thread_id, ())
        next_order = len(existing)
        combined = existing + (
            HistoryTurn(role="user", content=user_message, order=next_order),
            HistoryTurn(
                role="assistant",
                content=assistant_message,
                order=next_order + 1,
            ),
        )
        self._turns[thread_id] = truncate_history(combined, max_history)


class ContextPolicy:
    """Deterministic assembly of routing, answer, execution, and trusted slices."""

    def __init__(self, max_history: int = DEFAULT_MAX_HISTORY):
        self.max_history = max_history

    def assemble(
        self,
        request: RequestContext,
        *,
        observations: tuple[Observation, ...] = (),
        verification_result: bool | None = None,
        attempts: int = 0,
    ) -> AgentContext:
        scope = request.trusted_scope
        history = truncate_history(request.history, self.max_history)
        return AgentContext(
            request=request,
            routing=RoutingContext(message=request.message, trusted_scope=scope),
            answer=AnswerContext(
                message=request.message,
                history=history,
                evidence=_trusted_evidence(observations, verification_result),
            ),
            execution=ExecutionContext(
                thread_id=request.thread_id,
                attempts=attempts,
                verification_result=verification_result,
            ),
            trusted_scope=scope,
        )

    def for_router(self, context: AgentContext) -> RoutingContext:
        return context.routing

    def for_answer(self, context: AgentContext) -> AnswerContext:
        return context.answer


def _trusted_evidence(
    observations: tuple[Observation, ...],
    verification_result: bool | None,
) -> tuple[ToolEvidence, ...]:
    if verification_result is not True or not observations:
        return ()
    last = observations[-1]
    if not last.success:
        return ()
    return (
        ToolEvidence(tool_name=last.tool_name, data=dict(last.data), trusted=True),
    )
