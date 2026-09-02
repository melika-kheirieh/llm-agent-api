# API Contract

HTTP response shapes. `POST /chat` remains `{ "response": string }` only.

Invalid **environment** (unsupported `LLM_PROVIDER`, unsupported `ROUTER_MODE`, non-positive `LLM_TIMEOUT_SECONDS`, missing `OPENAI_API_KEY` for OpenAI) fails **process startup** via `ConfigurationError`. That is not an HTTP status.

---

## POST /chat

### Request

**Content-Type:** `application/json`

```json
{
  "message": "User question"
}
```

### Validation

* `message` is **required** → missing field **422**
* `message` must be a **non-empty string** after strip → empty **400** `"message is required"`

### Success (200 OK)

```json
{
  "response": "LLM generated answer"
}
```

No `run_id` in the body. Chat and `ExecutionTrace` are persisted in **one transaction** (`save_chat_and_trace`). If that write fails, neither row is committed.

### Errors

| Status | When |
| --- | --- |
| 400 | Empty `message` |
| 422 | Schema mismatch (e.g. missing `message`) |
| 502 | Upstream model failure or model timeout |
| 503 | Persistence failure (chat + trace unit) |
| 500 | Unhandled internal error |

**503** `"Database unavailable"` means the agent run finished but the atomic persist did not.

---

## GET /runs/{run_id}

Returns the persisted execution trace. Does not return the chat `response`.

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

`decision` is `"direct"` or `"use_tool"`. Review paths use `needs_human_review`.

### Errors

* **404** `"run not found"`
* **503** `"Database unavailable"` when the read fails

---

## GET /health

Process liveness. No database, no LLM.

### Success (200 OK)

```json
{
  "status": "ok"
}
```

Docker `HEALTHCHECK` uses this endpoint.

---

## GET /ready

Readiness: `SELECT 1` against the configured database.

### Success (200 OK)

```json
{
  "status": "ok"
}
```

### Errors

* **503** `"Database unavailable"`

---

## Status map

* 400 → business validation
* 422 → schema validation
* 404 → unknown run
* 502 → external LLM
* 503 → database (persist or `/ready`)
* 500 → internal
* startup `ConfigurationError` → process does not listen
