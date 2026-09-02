# Design — LLM Agent API

This project implements a production-leaning FastAPI service that runs an async LLM agent and stores both chat messages and execution traces.

The goal is **clarity and correctness**, not feature breadth.

---

## API Surface

**POST `/chat`** — `{ "response": "..." }` only. Empty message → `400`. Missing field → `422`. The body does not include `run_id`.

**GET `/runs/{run_id}`** — persisted `ExecutionTrace`, or `404`.

**GET `/health`** — process liveness. No database, no LLM.

**GET `/ready`** — `SELECT 1` against SQLite. `503` if the database is unavailable.

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
validate_startup() → init_db() → init_runtime()
  ↓
AsyncAgentRuntime.run_with_trace()
  → Router (AgentRouter default via ROUTER_MODE=keyword; LlmAgentRouter when ROUTER_MODE=llm)
       LlmAgentRouter → AsyncLLMClient.generate_structured
       DIRECT  → AsyncLLMClient.generate
       USE_TOOL → AgentTool.execute
                → Observation
                → ToolVerifier
                → RecoveryPolicy (retry or review)
  → ExecutionTrace
  ↓
save_chat_and_trace()  — one AsyncSession, one commit
  chat_messages + agent_runs
```

**Key properties**

* The API layer is provider-agnostic
* `AsyncAgentRuntime` is the execution source of truth
* LLM providers implement `AsyncLLMClient` (`generate` and `generate_structured`)
* Persistence is isolated behind the repository (`save_chat_and_trace`, `get_trace`)

---

## Core Flow

1. Receive `message` via `POST /chat`
2. Validate input (reject missing or empty message)
3. `AsyncAgentRuntime` routes the request:
   * **DIRECT** — generate an answer with the async LLM provider
   * **USE_TOOL** — run `work_order_lookup`, record an observation, verify the result
   * Unverified or exhausted retries return `"The request could not be verified."`
4. Persist chat row and `ExecutionTrace` in **one transaction** (`save_chat_and_trace`)
5. Return `{ "response" }` only

If that transaction fails, neither row is committed and the API returns `503`.

Evaluation compares a golden `Trajectory` (action, tool, arguments, verification,
attempts, recovery, outcome, events) against the same loop. Default cases use the
keyword router; LLM-routing cases inject `LlmAgentRouter` and a fake that returns
JSON text (or implements `generate_structured`). A separate comparison suite runs
the same messages through both strategies and scores action, tool, arguments, and
failure class — not answer text.

---

## Agent Core v1

The live runtime is explicit, not a hidden graph:

* **Router** — `Router` protocol (`async route(request) -> AgentDecision`). Production default is `AgentRouter` (`ROUTER_MODE=keyword`: `"work order"` / `"maintenance"` → `work_order_lookup`). `ROUTER_MODE=llm` wires `LlmAgentRouter` in `build_runtime()` without code changes. `LlmAgentRouter` asks the provider for a typed `RoutingOutput`, then checks allowed tools and domain arguments. It is not an LLM planner for the rest of the loop.
* **Structured output** — `AsyncLLMClient.generate_structured(prompt, schema)` returns a Pydantic instance. JSON parse and schema validation live in the provider layer (`app/llm/structured.py`). Callers do not `json.loads` model text.
* **Tools** — async `AgentTool` protocol; `work_order_lookup` is an in-process stub (always `open` / `plumbing` when an ID is present)
* **Observation** — tool outcome attached to `AgentState`
* **Verification** — domain-aware: required fields, requested `work_order_id` match, and allowed status. Not a second model
* **Recovery** — `RecoveryPolicy(max_attempts=2)` retries retryable failures (including tool timeouts), then human review. `ESCALATE` and `FAIL` both surface as the same review message today
* **Timeouts** — model `generate` and tool `execute` each have their own `asyncio.timeout`. Persistence is outside both. `CancelledError` is never wrapped as a model failure
* **Failure taxonomy** — `FailureClass` on state/trace (`model_timeout`, `tool_timeout`, `model_error`, `tool_error`, `verification_failure`, …)
* **Context policy** — deterministic assembly of routing, answer, execution, and trusted-scope slices. Raw tool output is not trusted until verification. `thread_id` is in-process only; history is bounded and not persisted
* **Traces** — `trace_from_state()` after each run; summary fields are persisted. `router_type`, `decision`, `selected_tool`, and `routing_ms` (time from `run_started` to `route_selected`) are on the in-memory trace and `chat_success` logs. They are not on `GET /runs`. Step events live on the in-memory `ExecutionTrace` and in logs (`event_names`).
* **Evaluation** — deterministic trajectory regression against the same `build_runtime` wiring, not answer-quality scoring. Routing comparison runs the same messages on keyword and LLM routers.

The DIRECT path still uses a local `analyze()` stub plus `respond()` for the LLM call. Routing and tools are the control loop; `analyze()` is not a product surface.

---

## Configuration and startup

Settings stay environment variables (no extra settings framework). `validate_startup()` runs in lifespan **before** `init_db` and `init_runtime`:

* `LLM_PROVIDER` must be `ollama` or `openai`
* `ROUTER_MODE` must be `keyword` or `llm` (default `keyword`)
* `LLM_TIMEOUT_SECONDS` must be a finite number `> 0`
* `OPENAI_API_KEY` is required when the provider is OpenAI

Invalid config raises `ConfigurationError` and the process does not start (no HTTP status). Docker `HEALTHCHECK` uses `/health`, not `/ready`.

---

## Persistence

Async SQLAlchemy (SQLite via `sqlite+aiosqlite`):

**`chat_messages`** — `message`, `response`, `created_at`

**`agent_runs`** — `run_id` (PK), `terminal_status`, `decision`, `selected_tool`, `verification_result`, `attempts`, `retry_count`, `outcome`, `failure_class`, `created_at`

`POST /chat` uses `save_chat_and_trace` (one session, one commit). Isolated `save_chat` / `save_trace` remain for tests and tooling. `GET /runs/{run_id}` uses `get_trace`.

---

## Error Strategy

* Client input error → `400`
* Schema validation → `422`
* Unknown `run_id` → `404`
* Upstream model failure or model timeout → `502`
* Tool timeout / tool error / verification failure → `200` with the review message; `failure_class` on the trace
* Persistence failure (chat write, trace write, `/ready`) → `503`
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

**Why tool verification?** A successful HTTP-shaped tool result is not automatically a valid answer. `ToolVerifier` is a domain gate (required fields, requested-id match, allowed status) so unverified output cannot be returned as if it were. It is **not** a second model.

**Why bounded retries?** Transient tool failures should retry once (`max_attempts=2`) and then stop. Unbounded loops hide bugs and burn the provider. After the budget, the run goes to human review with a fixed message.

**Why persist execution traces?** Logs explain a single process. `agent_runs` makes `run_id`, decision, tool, verification, attempts, and outcome queryable after restart. Chat clients still only need `{ "response" }`; operators use `GET /runs/{run_id}`. Chat and trace share one transaction so a persist failure cannot leave a chat row without a run.

**Why no persistent memory / RAG / LangGraph / multi-agent?** Those layers are real products, not prerequisites for a correct control loop. This runtime keeps an in-process, bounded thread buffer for optional previous turns. It is not durable memory, retrieval, or a second agent. LangGraph would hide the loop this repo is meant to show. Specialists and `DELEGATE` are future routing actions, not stubs in the tree. Workers/RabbitMQ are a different execution topology on top of this in-process runtime.

---

## Explicit Non-Goals

Deferred (documentation only; no placeholder modules):

* Conversation memory persisted across processes
* Checkpoints
* Specialists and `DELEGATE`
* Distributed workers / RabbitMQ
* RAG or vector databases
* LangChain / LangGraph
* Authentication, streaming, UI

---

## Design Philosophy

* Prefer simple, explicit abstractions over cleverness
* Optimize for readability and ease of review
* Keep execution predictable and debuggable
* Avoid premature complexity (features or infrastructure)
