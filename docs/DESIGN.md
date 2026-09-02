# Design — LLM Agent API

This project implements a production-leaning FastAPI service that runs an async LLM agent and stores chat messages plus execution traces.

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
  "response": "LLM generated answer"
}
```

Invalid or empty input is rejected with `400 Bad Request`. The success payload stays `{ "response": "..." }`.

**GET `/runs/{run_id}`**

Returns the persisted execution trace for a completed run, or `404` if the id is unknown.

---

## Architecture (Mental Model)

```
Client
  ↓
FastAPI (POST /chat)
  ↓
AsyncAgentRuntime.run_with_trace()
  ↓
AgentRouter
  ├─ DIRECT → AsyncLLMClient (Ollama / OpenAI)
  └─ USE_TOOL → work_order_lookup
                  ↓
                Observation → ToolVerifier → RecoveryPolicy
  ↓
ExecutionTrace
  ↓
Persistence
  ├─ chat_messages
  └─ agent_runs
```

**Key properties**

* The API layer is **provider-agnostic**
* `AsyncAgentRuntime` owns orchestration
* LLM providers are accessed through `AsyncLLMClient`
* Tools, verification, and recovery are explicit steps
* Each layer has a clear responsibility and boundary

---

## Core Flow

1. Receive `message` via `POST /chat`
2. Validate input (reject missing or empty message with `400`)
3. Execute `AsyncAgentRuntime.run_with_trace(message)`:
   * Route to `DIRECT` or `USE_TOOL`
   * `DIRECT` calls the async LLM provider
   * `USE_TOOL` executes the selected tool, records an observation, verifies the result, and retries at most once when the failure is retryable
   * Unverified tool results return a fixed review message
4. Persist the chat row and the `ExecutionTrace` (`agent_runs`)
5. Return `{ "response": ... }`
6. Inspect a run later with `GET /runs/{run_id}`

The whole runtime call is wrapped in a timeout (`LLM_TIMEOUT_SECONDS`).

---

## Agent Runtime

`AsyncAgentRuntime` is the execution source of truth.

* Router decides `DIRECT` vs `USE_TOOL` from the message
* Tool path uses `Observation`, `ToolVerifier`, and `RecoveryPolicy(max_attempts=2)`
* Context policy selects non-empty observations from the **current run only** (no conversation history)
* `run_with_trace()` maps `AgentState` to an `ExecutionTrace`
* Evaluation uses the same `build_runtime()` wiring with a fake LLM

The HTTP chat contract does not expose these internals.

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

Async SQLAlchemy stores:

* `chat_messages`: `message`, `response`, `created_at`
* `agent_runs`: `run_id`, terminal status, decision, selected tool, verification, attempts, retry count, outcome, failure class, `created_at`

SQLite (`sqlite+aiosqlite`) is chosen because it:

* Requires zero setup
* Is easy to inspect locally
* Keeps operational complexity low

---

## Error Strategy

The API exposes explicit failure boundaries:

* Client input error → `400`
* Unknown run id → `404`
* Upstream LLM failure → `502`
* Persistence failure → `503`
* Unexpected internal error → `500`

This separation ensures failures are:

* easier to debug
* easier to reason about
* correctly attributed to their source

---

## Observability (Intentionally Minimal)

To avoid over-engineering:

* Structured JSON logs
* Request latency logging (`latency_ms`)
* Execution traces on each successful chat
* Queryable `agent_runs` rows

No tracing frameworks or metrics stacks are included.

---

## Explicit Non-Goals (Scope Control)

The following are deferred and exist only as documentation, not as modules:

* Conversation memory / thread context
* Checkpoints
* Specialists and `DELEGATE`
* RabbitMQ, workers, or distributed execution
* RAG or vector databases
* LangChain / LangGraph
* Authentication, streaming, or a UI

These omissions keep the system simple, testable, and easy to review.

---

## Design Philosophy

* Prefer simple, explicit abstractions over cleverness
* Optimize for readability and ease of review
* Keep execution predictable and debuggable
* Avoid premature complexity (features or infrastructure)
