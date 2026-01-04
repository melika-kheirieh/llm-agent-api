# Design — LLM Agent API

This project implements a minimal, production-leaning FastAPI service that runs an LLM-backed agent and stores chat messages.

The goal is **clarity and correctness**, not feature breadth.

---

## API Surface

**Endpoint**

POST `/chat`

**Request**
```json
{
  "message": "User question"
}
````

**Response**

```json
{
  "response": "LLM generated answer"
}
```

Invalid or empty input is rejected with `400 Bad Request`.

---

## Architecture (Mental Model)

```
Client
  ↓
FastAPI  (POST /chat)
  ↓
Agent.run()
  ↓
LLMClient (interface)
  ├─ OllamaClient
  └─ OpenAIClient
  ↓
Persistence (SQLite)
```

Key property:
The API layer is **provider-agnostic**.
LLM selection happens only via environment variables.

---

## Core Flow

1. Receive `message` via `POST /chat`
2. Validate input (reject missing or empty message with `400`)
3. Run agent pipeline:

   * `analyze(message)`
   * `respond(message, analysis)` → LLM call
4. Persist `{message, response, timestamp}`
5. Return `{response}`

---

## Agent Abstraction

The agent is intentionally minimal:

* A single, explicit pipeline (`analyze → respond`)
* No implicit retries or hidden logic
* Designed to be extended later with:

  * Tools
  * Memory
  * Multi-step workflows

The current implementation favors transparency over sophistication.

---

## Provider Selection (Configuration)

Runtime behavior is configured exclusively via environment variables:

* `LLM_PROVIDER=ollama`

  * `OLLAMA_BASE_URL`
  * `OLLAMA_MODEL`

* `LLM_PROVIDER=openai`

  * `OPENAI_API_KEY`
  * `OPENAI_MODEL`
  * Optional `OPENAI_BASE_URL`

This keeps deployment simple and avoids leaking provider concerns into the API layer.

---

## Persistence

A minimal database layer stores chat history with fields:

* `message`
* `response`
* `timestamp`

SQLite is chosen for this task because it:

* Requires zero setup
* Is easy to inspect locally
* Keeps operational complexity low

---

## Error Strategy

The API exposes explicit and intentional failure modes:

* Invalid input (missing or empty `message`) → `400`
* Upstream LLM failure → `502`
* Persistence / database failure → `503`
* Unexpected internal error → `500`

This separation helps distinguish user errors, upstream issues, and internal bugs.

---

## Observability (Intentionally Minimal)

To avoid over-engineering:

* Structured JSON logs
* Request latency logging (`latency_ms`)
* Event-style success/failure logs

No tracing frameworks or metrics stacks are included in this task.

---

## Explicit Non-Goals (Scope Control)

The following features are **deliberately out of scope**:

* Retrieval-Augmented Generation (RAG) or vector databases
* Authentication or rate limiting
* Streaming responses or WebSockets
* Multi-user session management
* OpenWebUI integration
  (the architecture is compatible, but not implemented)

These omissions are intentional to keep the solution focused and reviewer-friendly.

---

## Design Philosophy

* Prefer simple, explicit abstractions over cleverness
* Optimize for readability and ease of review
* Keep execution predictable and debuggable
* Avoid premature infrastructure or feature complexity
