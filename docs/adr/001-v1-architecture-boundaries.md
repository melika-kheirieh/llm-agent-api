# ADR 001: V1 Architecture Boundaries

## Status

Accepted

## Context

The project is a small LLM-backed FastAPI service. Agent Core v1 should keep clear boundaries, testability, and predictable behavior. The live execution path is async and includes routing, a tool loop, verification, bounded recovery, and persisted traces.

## Decision

V1 keeps the following boundaries:

- **API** handles HTTP concerns and request validation. `POST /chat` returns `{ "response" }` only. `GET /runs/{run_id}` returns a persisted trace.
- **AsyncAgentRuntime** owns orchestration: deterministic keyword router → DIRECT or tool execution → observation → structural verification → recovery → `ExecutionTrace`.
- **LLM providers** implement `AsyncLLMClient`. The API does not import vendor clients.
- **Persistence** stays behind the repository: `save_chat`, `save_trace`, `get_trace` on async SQLAlchemy.
- **Evaluation** uses the same `build_runtime` wiring with a fake LLM.

## Non-goals for V1

The following are intentionally deferred (documentation only; no placeholder modules):

- conversation memory / thread context
- checkpoints
- specialists and `DELEGATE`
- distributed workers / RabbitMQ
- RAG and vector databases
- LangChain / LangGraph
- streaming responses
- production authentication

## Consequences

The live tree matches what the service actually runs. Future milestones can add memory, specialists, or a broker without changing the HTTP chat contract or the current in-process runtime.
