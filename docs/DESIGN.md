# Design — LLM Agent API

This project implements a production-leaning FastAPI service that runs an async LLM agent and stores both chat messages and execution traces.

The goal is **clarity and correctness**, not feature breadth.

---

## API Surface

**POST `/chat`**

```json
{
  "message": "User question"
}
```

```json
{
  "response": "Agent answer"
}
```

Invalid or empty input is rejected with `400 Bad Request`.

The chat body **does not include `run_id` or other trace fields**. That is intentional: `/chat` stays a stable answer contract for clients. Traces are an observability surface (`chat_success` logs, `agent_runs`, `GET /runs/{run_id}`), not part of the chat payload.

**GET `/runs/{run_id}`**

Returns the persisted `ExecutionTrace` for that run, or `404` if unknown.

---

## Architecture (Mental Model)

```
Client
  ↓
FastAPI
  POST /chat
  GET  /runs/{run_id}
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
Persistence (async SQLAlchemy / SQLite)
  chat_messages
  agent_runs
```

**Key properties**

* The API layer is provider-agnostic
* `AsyncAgentRuntime` is the execution source of truth
* LLM providers implement `AsyncLLMClient`
* Persistence is isolated behind the repository (`save_chat`, `save_trace`, `get_trace`)

---

## Core Flow

1. Receive `message` via `POST /chat`
2. Validate input (reject missing or empty message)
3. `AsyncAgentRuntime` routes the request:
   * **DIRECT** — generate an answer with the async LLM provider
   * **USE_TOOL** — run `work_order_lookup`, record an observation, verify the result
   * Unverified or exhausted retries return a review message (`"The request could not be verified."`)
4. Persist `{message, response}` on `chat_messages`
5. Persist the `ExecutionTrace` on `agent_runs`
6. Return `{response}` only

Evaluation uses `build_runtime(fake LLM)` so cases exercise the same loop.

---

## Agent Core v1

The live runtime is explicit, not a hidden graph:

* **Router** — deterministic keyword match (`"work order"` / `"maintenance"`), not an LLM planner
* **Tools** — async `AgentTool` protocol; `work_order_lookup` is an in-process stub (always `open` / `plumbing` when an ID is present)
* **Observation** — tool outcome attached to `AgentState`
* **Verification** — structural: `result.success` and non-empty `data`. Not a second model or domain policy
* **Recovery** — `RecoveryPolicy(max_attempts=2)` retries retryable failures, then human review. `ESCALATE` and `FAIL` both surface as the same review message today
* **Context policy** — drops empty items from the **current run** only (no conversation history)
* **Traces** — `trace_from_state()` after each run; logged and persisted
* **Evaluation** — regression on terminal `AgentStatus` against the same `build_runtime` wiring, not answer-quality scoring

The DIRECT path still uses a local `analyze()` stub plus `respond()` for the LLM call. Routing and tools are the control loop; `analyze()` is not a product surface.

---

## Provider Selection (Configuration)

Runtime behavior is configured exclusively via environment variables:

**Ollama (local)**

* `LLM_PROVIDER=ollama`
* `OLLAMA_BASE_URL`
* `OLLAMA_MODEL`

**OpenAI (cloud)**

* `LLM_PROVIDER=openai`
* `OPENAI_API_KEY`
* `OPENAI_MODEL`
* Optional `OPENAI_BASE_URL`

This approach:

* Keeps the API layer clean
* Avoids leaking provider-specific logic
* Makes switching providers trivial

---

## Persistence

Async SQLAlchemy (SQLite via `sqlite+aiosqlite`) stores:

**`chat_messages`**

* `message`
* `response`
* `created_at`

**`agent_runs`**

* `run_id` (primary key)
* `terminal_status`, `decision`, `selected_tool`, `verification_result`
* `attempts`, `retry_count`, `outcome`, `failure_class`
* `created_at`

SQLite is chosen because it requires zero setup and is easy to inspect locally.

---

## Error Strategy

The API exposes explicit failure boundaries:

* Client input error → `400`
* Unknown `run_id` → `404`
* Upstream LLM failure → `502`
* Persistence failure → `503`
* Unexpected internal error → `500`

---

## Observability (Intentionally Minimal)

* Structured JSON logs
* Request latency logging (`latency_ms`)
* `ExecutionTrace` fields on successful chat logs
* Queryable runs via `GET /runs/{run_id}`

No external tracing or metrics stacks are required.

---

## Explicit Non-Goals (Scope Control)

Deferred to later milestones (documentation only):

* Conversation memory / thread context
* Checkpoints
* Specialists and `DELEGATE`
* Distributed workers / RabbitMQ
* RAG or vector databases
* LangChain / LangGraph
* Authentication, streaming, UI

These omissions keep the current system simple, testable, and honest about what runs.

---

## Design Philosophy

* Prefer simple, explicit abstractions over cleverness
* Optimize for readability and ease of review
* Keep execution predictable and debuggable
* Avoid premature complexity (features or infrastructure)
