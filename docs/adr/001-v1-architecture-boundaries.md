# ADR 001: V1 Architecture Boundaries

## Status
Accepted

## Context

The project is a small LLM-backed FastAPI service. Agent Core v1 should keep clear boundaries, testability, and predictable behavior while supporting a real execution loop (routing, tools, verification, recovery, traces).

## Decision

V1 keeps the following boundaries:

- API layer handles HTTP concerns and request validation (`POST /chat`, `GET /runs/{run_id}`).
- `AsyncAgentRuntime` owns application-level orchestration.
- `AgentRouter` chooses `DIRECT` or `USE_TOOL` before any LLM or tool call.
- LLM providers are accessed through `AsyncLLMClient` instead of being coupled to the API.
- Tools, observations, verification, and bounded recovery stay inside the runtime.
- Persistence remains isolated behind an async database layer (`chat_messages`, `agent_runs`).
- Evaluation runs against the same runtime wiring, with a fake LLM.

`POST /chat` continues to return only `{ "response": "..." }`. Traces are a side effect, queryable via `GET /runs/{run_id}`.

## Non-goals for V1

The following are intentionally deferred. They must not appear as empty modules that look like live features:

- conversation memory / thread context
- checkpoints
- specialists and `DELEGATE`
- RabbitMQ, workers, or distributed execution
- RAG and vector databases
- LangChain / LangGraph
- streaming responses
- production authentication

## Consequences

The live tree matches the live runtime. Reviewers can follow API → runtime → router/tools/LLM → persistence without prototype leftovers. Later milestones can add memory, specialists, or workers on top of a stable async core.
