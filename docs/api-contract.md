# API Contract

HTTP response shapes for existing endpoints. `POST /chat` remains `{ "response": string }` only.

---

## POST /chat

### Request

**Content-Type:** `application/json`

```json
{
  "message": "User question"
}
```

### Validation Rules

* `message` is **required**
* `message` must be a **non-empty string**

### Validation behavior

* Missing `message` → **422 Unprocessable Entity** (handled by FastAPI)
* Empty `message` → **400 Bad Request** (business-level validation)

### Success (200 OK)

```json
{
  "response": "LLM generated answer"
}
```

The chat body does not include `run_id` or other trace fields. Chat stays an answer-only contract; traces are queried separately from `agent_runs` via `GET /runs/{run_id}` (and appear on the `chat_success` log line).

### Errors

#### 400 Bad Request — Business validation error

Returned when the input is structurally valid but semantically invalid.

Example: `message` is an empty string

```json
{
  "detail": "message is required"
}
```

#### 422 Unprocessable Entity — Schema validation error

Returned when the request body does not match the expected schema (for example, `message` is missing).

#### 502 Bad Gateway — Upstream LLM failure

Returned when the LLM provider (OpenAI or Ollama) fails.

This indicates:

* the request was valid
* the failure occurred in an external dependency

#### 503 Service Unavailable — Persistence failure

Returned when the database is unavailable or write operations fail (`save_chat` or `save_trace`).

This indicates:

* the agent pipeline succeeded
* but persistence could not be completed

#### 500 Internal Server Error — Unexpected failure

Returned for unhandled or unknown internal errors.

---

## GET /runs/{run_id}

Returns the persisted execution trace for a completed run.

### Success (200 OK)

```json
{
  "run_id": "…",
  "terminal_status": "completed",
  "decision": "direct",
  "selected_tool": null,
  "verification_result": null,
  "attempts": 0,
  "retry_count": 0,
  "outcome": "success",
  "failure_class": null,
  "created_at": "…"
}
```

`decision` is `"direct"` or `"use_tool"`. Tool runs may set `selected_tool`, `verification_result`, `attempts`, and `retry_count`. Review paths use `terminal_status` / `outcome` of `needs_human_review`.

This endpoint does not return the chat `response`.

### Errors

#### 404 Not Found

Unknown `run_id`:

```json
{
  "detail": "run not found"
}
```

#### 503 Service Unavailable — Persistence failure

Returned when the database cannot be read.

---

## Design Rationale

* **422 for schema validation** — FastAPI's built-in validation for structural request errors
* **400 for business validation** — empty `message` is handled explicitly
* **404 for missing runs** — traces are queryable but not guaranteed for every client
* **502 for LLM failures** — providers are upstream dependencies
* **503 for persistence issues** — database failures are availability problems
* **Clear failure boundaries**
  * 400 → business logic
  * 422 → schema validation
  * 404 → unknown run
  * 502 → external dependency (LLM)
  * 503 → infrastructure (database)
  * 500 → internal application
