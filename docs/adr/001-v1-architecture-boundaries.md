# ADR 001: V1 Architecture Boundaries

## Status

Accepted

## Context

The project is a small LLM-backed FastAPI service. Agent Core v1 should keep clear boundaries, testability, and predictable behavior. The live path is async: keyword routing, a stub tool loop, domain-aware verification, bounded recovery, persisted traces, fail-fast config, and health/readiness probes.

## Decision

V1 keeps the following boundaries:

- **API** handles HTTP. `POST /chat` returns `{ "response" }` only. `GET /runs/{run_id}` returns a persisted trace. `GET /health` is liveness (no I/O). `GET /ready` is `SELECT 1`.
- **Startup** validates settings (`LLM_PROVIDER`, `ROUTER_MODE`, timeout, `DATABASE_URL`, OpenAI key when required) before `init_db` (Alembic) and `init_runtime`.
- **AsyncAgentRuntime** is the execution boundary HTTP and evaluation still call. LangGraph owns **transitions**. Nodes wrap `Router`, tools, `ToolVerifier`, `RecoveryPolicy`, and answer generation. Tools receive `TrustedScope` separately from model arguments. `build_runtime()` selects `AgentRouter` or `LlmAgentRouter` from `ROUTER_MODE` (default `keyword`). An explicit `router=` argument still overrides config.
- **LLM providers** implement `AsyncLLMClient` (`generate` for free text, `generate_structured` for typed schema output). JSON/schema parse lives in the provider layer. The API does not import vendor clients. The router validates allowed tools and domain arguments after the schema is valid.
- **Persistence** uses async SQLAlchemy (SQLite locally, PostgreSQL in Compose/production). Schema is Alembic-managed. `POST /chat` writes chat, run summary, and sanitized step events in one transaction (`save_chat_and_trace`). `get_trace` serves `/runs`. Router type and routing latency are log/trace fields, not `agent_runs` columns.
- **Evaluation** uses the same `build_runtime` wiring with a fake LLM. Routing comparison scores action, tool, arguments, and failure class for keyword vs LLM on the same messages.

## Non-goals for V1

Deferred (documentation only; no placeholder modules):

- conversation memory persisted across processes
- checkpoints
- specialists and `DELEGATE`
- distributed workers / RabbitMQ
- RAG and vector databases
- LangChain chains, embeddings, or retrieval
- LangGraph checkpoints, multi-agent workflows, or durable graph memory
- streaming responses
- production authentication

See [Design Decisions](../DESIGN.md#design-decisions) for why.

## Consequences

The live tree matches what the service actually runs. HTTP (`POST /chat` → `{ "response" }`) and trajectory evaluation stay on `AsyncAgentRuntime`. LangGraph is an in-process transition adapter, not a second product surface. Future milestones can add memory, specialists, or a broker without changing the HTTP chat contract.
