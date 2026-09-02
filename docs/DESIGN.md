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
  → AgentRouter
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
* LLM providers implement `AsyncLLMClient`
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
attempts, recovery, outcome) against the same loop. It does not score answer text.

---

## Agent Core v1

The live runtime is explicit, not a hidden graph:

* **Router** — deterministic keyword match (`"work order"` / `"maintenance"`), not an LLM planner
* **Tools** — async `AgentTool` protocol; `work_order_lookup` is an in-process stub (always `open` / `plumbing` when an ID is present)
* **Observation** — tool outcome attached to `AgentState`
* **Verification** — domain-aware: required fields, requested `work_order_id` match, and allowed status. Not a second model
* **Recovery** — `RecoveryPolicy(max_attempts=2)` retries retryable failures, then human review. `ESCALATE` and `FAIL` both surface as the same review message today
* **Context policy** — drops empty items from the **current run** only (no conversation history)
* **Traces** — `trace_from_state()` after each run; logged and persisted with the chat row
* **Evaluation** — deterministic trajectory regression against the same `build_runtime` wiring, not answer-quality scoring

The DIRECT path still uses a local `analyze()` stub plus `respond()` for the LLM call. Routing and tools are the control loop; `analyze()` is not a product surface.

---

## Configuration and startup

Settings stay environment variables (no extra settings framework). `validate_startup()` runs in lifespan **before** `init_db` and `init_runtime`:

* `LLM_PROVIDER` must be `ollama` or `openai`
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
* Upstream LLM failure / timeout → `502`
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

**Why async?** Provider I/O and SQLite access are wait-bound. An async FastAPI process can overlap `/chat` requests, apply `asyncio.timeout` around a run, and propagate `CancelledError` without wrapping it as an LLM failure. The alternative (thread-per-request around sync HTTP) hid cancellation and timeout ownership.

**Why deterministic routing instead of an LLM planner?** V1 needs a testable, cheap first boundary: `"work order"` / `"maintenance"` → `work_order_lookup`, otherwise DIRECT. An LLM planner would add latency, cost, and non-determinism before the first tool exists. The router is **keyword matching**, not function-calling.

**Why tool verification?** A successful HTTP-shaped tool result is not automatically a valid answer. `ToolVerifier` is a domain gate (required fields, requested-id match, allowed status) so unverified output cannot be returned as if it were. It is **not** a second model.

**Why bounded retries?** Transient tool failures should retry once (`max_attempts=2`) and then stop. Unbounded loops hide bugs and burn the provider. After the budget, the run goes to human review with a fixed message.

**Why persist execution traces?** Logs explain a single process. `agent_runs` makes `run_id`, decision, tool, verification, attempts, and outcome queryable after restart. Chat clients still only need `{ "response" }`; operators use `GET /runs/{run_id}`. Chat and trace share one transaction so a persist failure cannot leave a chat row without a run.

**Why no memory / RAG / LangGraph / multi-agent?** Those layers are real products, not prerequisites for a correct control loop. Memory and RAG change retrieval, not routing. LangGraph would hide the loop this repo is meant to show. Specialists and `DELEGATE` are future routing actions, not stubs in the tree. Workers/RabbitMQ are a different execution topology on top of this in-process runtime.

---

## Explicit Non-Goals

Deferred (documentation only; no placeholder modules):

* Conversation memory / thread context
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
