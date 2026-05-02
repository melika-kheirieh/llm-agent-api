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
FastAPI (POST /chat)
  ↓
Agent.run()
  ↓
LLMClient (interface)
  ├─ OllamaClient
  └─ OpenAIClient
  ↓
Persistence (SQLite)
```

**Key properties**

* The API layer is **provider-agnostic**
* The agent encapsulates application logic
* LLM providers are treated as external dependencies
* Each layer has a clear responsibility and boundary

---

## Core Flow

1. Receive `message` via `POST /chat`
2. Validate input (reject missing or empty message with `400`)
3. Execute agent pipeline:

   * `analyze(message)`
   * `respond(message, analysis)` → LLM call
4. Persist `{message, response, timestamp}`
5. Return `{response}`

---

## Agent Abstraction

The agent is intentionally minimal:

* A single, explicit pipeline (`analyze → respond`)
* No implicit retries or hidden control flow
* Fully testable without real LLM calls

Designed for future extension with:

* Tools
* Memory
* Multi-step workflows

The current implementation favors transparency over sophistication.

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

A minimal database layer stores chat history:

* `message`
* `response`
* `timestamp`

SQLite is chosen because it:

* Requires zero setup
* Is easy to inspect locally
* Keeps operational complexity low

---

## Error Strategy

The API exposes explicit failure boundaries:

* Client input error → `400`
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
* Event-style success/failure logs

No tracing frameworks or metrics stacks are included.

---

## Explicit Non-Goals (Scope Control)

The following features are deliberately out of scope:

* Retrieval-Augmented Generation (RAG) or vector databases
* Authentication or rate limiting
* Streaming responses or WebSockets
* Multi-user session management
* UI / OpenWebUI integration

These omissions are intentional to keep the system:

* simple
* testable
* easy to review

---

## Design Philosophy

* Prefer simple, explicit abstractions over cleverness
* Optimize for readability and ease of review
* Keep execution predictable and debuggable
* Avoid premature complexity (features or infrastructure)
