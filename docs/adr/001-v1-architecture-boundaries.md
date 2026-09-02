# ADR 001: V1 Architecture Boundaries

## Status

Accepted

## Context

The project is a small LLM-backed FastAPI service. Agent Core v1 should keep clear boundaries, testability, and predictable behavior. The live path is async: keyword routing, a stub tool loop, domain-aware verification, bounded recovery, persisted traces, fail-fast config, and health/readiness probes.

## Decision

V1 keeps the following boundaries:

- **API** handles HTTP. `POST /chat` returns `{ "response" }` only. `GET /runs/{run_id}` returns a persisted trace. `GET /health` is liveness (no I/O). `GET /ready` is `SELECT 1`.
- **Startup** validates settings (`LLM_PROVIDER`, timeout, OpenAI key when required) before `init_db` and `init_runtime`.
- **AsyncAgentRuntime** owns orchestration: deterministic keyword router → DIRECT or tool execution → observation → domain-aware verification → recovery → `ExecutionTrace`.
- **LLM providers** implement `AsyncLLMClient`. The API does not import vendor clients.
- **Persistence** uses async SQLAlchemy. `POST /chat` writes chat and trace in one transaction (`save_chat_and_trace`). `get_trace` serves `/runs`.
- **Evaluation** uses the same `build_runtime` wiring with a fake LLM.

## Non-goals for V1

Deferred (documentation only; no placeholder modules):

- conversation memory / thread context
- checkpoints
- specialists and `DELEGATE`
- distributed workers / RabbitMQ
- RAG and vector databases
- LangChain / LangGraph
- streaming responses
- production authentication

See [Design Decisions](../DESIGN.md#design-decisions) for why.

## Consequences

The live tree matches what the service actually runs. Future milestones can add memory, specialists, or a broker without changing the HTTP chat contract or the current in-process runtime.
