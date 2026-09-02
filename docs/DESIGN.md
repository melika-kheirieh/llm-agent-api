# Design — LLM Agent API

This project implements a production-leaning FastAPI service that runs an async LLM agent and stores both chat messages and execution traces.

The goal is **clarity and correctness**, not feature breadth.

---

## API Surface

**POST `/chat`** — `{ "response": "..." }` only. Empty message → `400`. Missing field → `422`. The body does not include `run_id`. Optional `X-Tenant-Id` / `X-Property-Id` headers become backend `TrustedScope` (demo propagation, not authentication). Successful responses set `X-Run-Id`.

**GET `/runs/{run_id}`** — persisted run summary and sanitized step events, or `404`.

**GET `/health`** — process liveness. No database, no LLM.

**GET `/ready`** — `SELECT 1` against the configured database. `503` if the database is unavailable.

---

## Architecture (Mental Model)

```
Client
  ↓
FastAPI
  POST /chat
  GET  /runs/{run_id}
  GET  /health
  GET  /ready
  ↓
validate_startup() → init_db() (Alembic upgrade) → init_runtime()
  ↓
AsyncAgentRuntime.run_with_trace()
  → LangGraph transitions (route_node → answer_node | tool_node → verify_node → answer_node | recovery_node)
       Router (AgentRouter default via ROUTER_MODE=keyword; LlmAgentRouter when ROUTER_MODE=llm)
       LlmAgentRouter → AsyncLLMClient.generate_structured
       DIRECT  → AsyncLLMClient.generate (answer_node)
       USE_TOOL → AgentTool.execute → Observation → ToolVerifier → RecoveryPolicy
  → ExecutionTrace
  ↓
save_chat_and_trace()  — one AsyncSession, one commit
  chat_messages + agent_runs + agent_run_events
```

**Key properties**

* The API layer is provider-agnostic
* `AsyncAgentRuntime` is the execution boundary HTTP and evaluation still call
* LangGraph owns **transitions only**; nodes wrap Router, tools, ToolVerifier, RecoveryPolicy, and answer generation
* LLM providers implement `AsyncLLMClient` (`generate` and `generate_structured`)
* Persistence is isolated behind the repository (`save_chat_and_trace`, `get_trace`)

---

## Core Flow

1. Receive `message` via `POST /chat`
2. Validate input (reject missing or empty message)
3. Copy `X-Tenant-Id` / `X-Property-Id` into backend `TrustedScope` (never from the message)
4. `AsyncAgentRuntime` runs the request on a compiled in-process graph:
   * **DIRECT** — `route_node` → `answer_node` (async LLM provider)
   * **USE_TOOL** — `tool_node` (`work_order_lookup` or `maintenance_policy_lookup`) → `verify_node` → `answer_node` or `recovery_node`
   * Unverified or exhausted retries return `"The request could not be verified."`
5. Persist chat row and `ExecutionTrace` in **one transaction** (`save_chat_and_trace`)
6. Return `{ "response" }` only, plus `X-Run-Id` when the run was persisted

If that transaction fails, no chat, run, or event rows are committed and the API returns `503`.

Evaluation compares a golden `Trajectory` (action, tool, arguments, verification,
attempts, recovery, outcome, events) against the same loop. Default cases use the
keyword router; LLM-routing cases inject `LlmAgentRouter` and a fake that returns
JSON text (or implements `generate_structured`). A separate comparison suite runs
the same messages through both strategies and scores action, tool, arguments, and
failure class — not answer text.

---

## Agent Core v1

The live runtime is explicit. LangGraph selects the next node; it does not replace the components:

* **Graph** — `app/agent/graph.py`. `GraphState` wraps `AgentState`. No checkpointer, no multi-agent graph, no RAG.
* **Router** — `Router` protocol (`async route(request) -> AgentDecision`). Production default is `AgentRouter` (`ROUTER_MODE=keyword`: `"policy"` → `maintenance_policy_lookup`; `"work order"` / `"maintenance"` → `work_order_lookup`). `ROUTER_MODE=llm` wires `LlmAgentRouter` in `build_runtime()` without code changes. `LlmAgentRouter` asks the provider for a typed `RoutingOutput`, then checks allowed tools and domain arguments. It is not an LLM planner for the rest of the loop.
* **Structured output** — `AsyncLLMClient.generate_structured(prompt, schema)` returns a Pydantic instance. JSON parse and schema validation live in the provider layer (`app/llm/structured.py`). Callers do not `json.loads` model text.
* **Tools** — async `AgentTool.execute(arguments, *, trusted_scope)`. `TrustedScope` is backend-provided and never taken from model arguments. `work_order_lookup` and `maintenance_policy_lookup` query an in-process catalog by scope + id/issue type.
* **Observation** — tool outcome attached to `AgentState`
* **Verification** — per-tool domain gate. Work orders: requested id, tenant/property match, required fields, allowed status. Policies: scope, required fields, version, freshness window, allowed action. Unknown tools never verify.
* **Recovery** — `RecoveryPolicy(max_attempts=2)` retries retryable failures (including tool timeouts), then human review. `ESCALATE` and `FAIL` both surface as the same review message today
* **Timeouts** — model `generate` and tool `execute` each have their own `asyncio.timeout`. Persistence is outside both. `CancelledError` is never wrapped as a model failure
* **Failure taxonomy** — `FailureClass` on state/trace (`model_timeout`, `tool_timeout`, `model_error`, `tool_error`, `verification_failure`, …)
* **Context policy** — deterministic assembly of routing, answer, execution, and trusted-scope slices. Raw tool output is not trusted until verification. `thread_id` is in-process only; history is bounded and not persisted
* **Traces** — `trace_from_state()` after each run; summary fields persist on `agent_runs` and sanitized step events persist on `agent_run_events`. `router_type` and `routing_ms` stay log/in-memory fields (not `agent_runs` columns). `GET /runs/{run_id}` returns the summary plus ordered events.
* **Evaluation** — deterministic trajectory regression against the same `build_runtime` wiring, not answer-quality scoring. Routing comparison runs the same messages on keyword and LLM routers.

The DIRECT path still uses a local `analyze()` stub plus `respond()` for the LLM call. Routing and tools are the control loop; `analyze()` is not a product surface.

---

## Configuration and startup

Settings stay environment variables (no extra settings framework). `validate_startup()` runs in lifespan **before** `init_db` and `init_runtime`:

* `LLM_PROVIDER` must be `ollama` or `openai`
* `ROUTER_MODE` must be `keyword` or `llm` (default `keyword`)
* `LLM_TIMEOUT_SECONDS` must be a finite number `> 0`
* `DATABASE_URL` must be non-empty (SQLite or PostgreSQL async URLs are normalized; other schemes pass through)
* `OPENAI_API_KEY` is required when the provider is OpenAI

Invalid config raises `ConfigurationError` and the process does not start (no HTTP status). Docker `HEALTHCHECK` uses `/health`, not `/ready`.

---

## Persistence

Async SQLAlchemy. Local default is SQLite (`sqlite+aiosqlite`). Production-like Compose uses PostgreSQL (`postgresql+asyncpg`). `DATABASE_URL` selects the backend; see [database.md](database.md).

Schema is applied with Alembic (`init_db` runs `upgrade head` before runtime init). Do not use `create_all` for application tables. Compose credentials are local development only. Multi-replica production should run migrations separately, not on every replica boot.

**`chat_messages`** — `message`, `response`, `created_at`

**`agent_runs`** — `run_id` (PK), `terminal_status`, `decision`, `selected_tool`, `verification_result`, `attempts`, `retry_count`, `outcome`, `failure_class`, `created_at`

**`agent_run_events`** — `run_id` (FK), `event_order`, `name`, `timestamp`, `metadata_json` (sanitized). Unique on (`run_id`, `event_order`).

`POST /chat` uses `save_chat_and_trace` (one session, one commit). Isolated `save_chat` / `save_trace` remain for tests and tooling. `GET /runs/{run_id}` uses `get_trace`. Event metadata is allowlisted: no tenant/property, tool payloads, or prompts. Raw observations stay on `AgentState` only.

---

## Error Strategy

* Client input error → `400`
* Schema validation → `422`
* Unknown `run_id` → `404`
* Upstream model failure or model timeout → `502`
* Tool timeout / retryable tool error / verification failure → `200` with the review message; `failure_class` on the trace
* Domain/security tool rejection (cross-tenant, wrong-property, missing scope) → same HTTP review path and `failure_class=tool_error`, distinguished by in-memory `error_code` (`cross_tenant`, `wrong_property`, …). Not a new `FailureClass`. Timeouts stay `tool_timeout`.
* Persistence failure (chat write, trace write, `/ready`) → `503`
* Unexpected internal error → `500`
* Invalid environment → process fails at startup

---

## Observability (Intentionally Minimal)

* Structured JSON logs
* Request latency (`latency_ms`)
* `ExecutionTrace` fields on successful chat logs
* Queryable runs via `GET /runs/{run_id}`
* `/health` vs `/ready` (liveness vs database)

---

## Design Decisions

**Why async?** Provider I/O and SQLite access are wait-bound. An async FastAPI process can overlap `/chat` requests, apply `asyncio.timeout` around **model** and **tool** calls separately, and propagate `CancelledError` without wrapping it as a model failure. Persistence runs after the agent returns and is not covered by those timeouts. The alternative (one timeout around the whole run) made tool hangs look like LLM failures.

**Why deterministic routing by default?** V1 production and eval still use keyword matching so the first boundary stays cheap and reproducible: `"work order"` / `"maintenance"` → `work_order_lookup`, otherwise DIRECT. `ROUTER_MODE=llm` selects `LlmAgentRouter` at process start without changing the HTTP contract. It is not function-calling or a multi-agent planner. LLM routing adds a structured model call before DIRECT/tool work; `routing_ms` on logs makes that extra latency visible without a metrics vendor.

**Why structured output at the provider boundary?** JSON parsing and Pydantic schema checks are model-output problems: the vendor may emit fenced text, invalid JSON, or extra fields. `generate_structured` owns that path so every caller gets a typed object or a `model_error`. The router still owns **routing** validation: allowed tools and domain argument rules (for example `work_order_id` must be a non-empty string). Schema-invalid output never becomes an `AgentDecision`. Domain-invalid output can carry a partial decision and is still classified as `model_error` today (`RoutingError` subclasses `ModelError`).

OpenAI tries native JSON-object formatting, then falls back to `generate()` plus parse if that request fails or returns empty text. Ollama sends `format=json` and falls back the same way on provider `ModelError` (HTTP/empty), not on parse failure. Timeouts and cancellation never fall back. Plain `generate()` is unchanged. Duck-typed fakes that only implement `generate()` still work through `generate_structured_from`.

**Why tool verification?** A successful HTTP-shaped tool result is not automatically a valid answer. `ToolVerifier` dispatches to a work-order gate or a policy gate (required fields, scope match, allowed status/action, policy freshness). It is **not** a second model and it does not accept unknown tools.

**Why TrustedScope is not in tool arguments?** Authorization is a backend fact. If `tenant_id` / `property_id` lived in model-generated arguments, the router could be talked into another tenant. Tools receive `TrustedScope` as a separate keyword argument; extra scope keys in routing JSON are a `RoutingError`. HTTP copies `X-Tenant-Id` / `X-Property-Id` onto that object. Those headers are demo scope propagation, not authentication: missing values still fail closed, and the user message cannot create scope.

**Why sanitize tool evidence?** Verified observations still contain tenant/property so the verifier can check scope. Answer context is a different audience: `ToolEvidence` drops those fields. Raw observations stay on `AgentState` for debugging. Traces log `error_code`, not `tenant_id`.

**Why no new FailureClass for cross-tenant?** Operational failures (timeout, retryable tool error) and domain/security rejections (cross-tenant, wrong-property) already diverge on retryability and payload. They share `tool_error` when the tool returns an envelope failure. Evaluation uses `error_code` plus `failure_class` so a cross-tenant run cannot match a timeout (`tool_timeout` / `error_code=tool_timeout`).

**Why bounded retries?** Transient tool failures should retry once (`max_attempts=2`) and then stop. Unbounded loops hide bugs and burn the provider. After the budget, the run goes to human review with a fixed message.

**Why persist execution traces?** Logs explain a single process. `agent_runs` plus `agent_run_events` make route, tools, verification, recovery, and outcome queryable after restart. Chat clients still only need `{ "response" }`; operators read `X-Run-Id` then `GET /runs/{run_id}`. Chat, run summary, and events share one transaction so a persist failure cannot leave a chat row without a run. This is not replay, memory, or a LangGraph checkpointer.

**Why LangGraph only for transitions?** The control loop was already correct as an explicit `AsyncAgentRuntime` method chain. Moving **edges** into LangGraph makes route / tool / verify / recover / answer paths visible as a graph without copying that logic into nodes. Nodes call the existing steps. There is no checkpointer, no multi-agent graph, and no LangChain chain. Tracing still uses `TraceEvent` on `AgentState`; it does not depend on LangGraph internals.

**Why no persistent memory / RAG / multi-agent?** Those layers are real products, not prerequisites for a correct control loop. This runtime keeps an in-process, bounded thread buffer for optional previous turns. It is not durable memory, retrieval, or a second agent. Specialists and `DELEGATE` are future routing actions, not stubs in the tree. Workers/RabbitMQ are a different execution topology on top of this in-process runtime.

---

## Explicit Non-Goals

Deferred (documentation only; no placeholder modules):

* Conversation memory persisted across processes
* Checkpoints
* Specialists and `DELEGATE`
* Distributed workers / RabbitMQ
* RAG or vector databases
* LangChain chains, embeddings, or retrieval
* LangGraph checkpoints, multi-agent workflows, or durable graph memory
* Authentication, streaming, UI

---

## Design Philosophy

* Prefer simple, explicit abstractions over cleverness
* Optimize for readability and ease of review
* Keep execution predictable and debuggable
* Avoid premature complexity (features or infrastructure)
