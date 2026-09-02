# API Contract

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

The success body is only `{ "response": "..." }`. Routing, tool use, retries, and traces are not included in this payload.

After a successful run the service also writes:

* a `chat_messages` row
* an `agent_runs` row for the execution trace

---

## GET /runs/{run_id}

Returns the persisted execution trace for a run.

### Success (200 OK)

```json
{
  "run_id": "...",
  "terminal_status": "completed",
  "decision": "direct",
  "selected_tool": null,
  "verification_result": null,
  "attempts": 0,
  "retry_count": 0,
  "outcome": "success",
  "failure_class": null,
  "created_at": "2026-09-02T12:00:00+00:00"
}
```

`decision` is `direct` or `use_tool`. `selected_tool` is set when the router chose a tool (currently `work_order_lookup`).

This response does **not** include the chat `response` text.

### 404 Not Found

Returned when `run_id` is unknown.

```json
{
  "detail": "run not found"
}
```

---

## Error Handling

The API distinguishes failures across different layers:

### 400 Bad Request — Business validation error

Returned when the input is structurally valid but semantically invalid.

Example:

* `message` is an empty string

```json
{
  "detail": "message is required"
}
```

---

### 422 Unprocessable Entity — Schema validation error

Returned when the request body does not match the expected schema.

Example:

* `message` field is missing

---

### 404 Not Found — Unknown run

Returned by `GET /runs/{run_id}` when the trace does not exist.

---

### 502 Bad Gateway — Upstream LLM failure

Returned when the LLM provider (e.g., OpenAI or Ollama) fails.

This indicates:

* the request was valid
* the failure occurred in an external dependency

---

### 503 Service Unavailable — Persistence failure

Returned when the database is unavailable or write/read operations fail.

On `POST /chat` this indicates:

* the agent pipeline succeeded
* but persistence could not be completed

---

### 500 Internal Server Error — Unexpected failure

Returned for unhandled or unknown internal errors.

---

## Design Rationale

* **422 for schema validation**
  FastAPI's built-in validation is used for structural request errors.

* **400 for business validation**
  Application-level validation (e.g., empty message) is handled explicitly.

* **404 for missing runs**
  Trace lookup is a read of durable `agent_runs` rows.

* **502 for LLM failures**
  LLM providers are treated as upstream dependencies.

* **503 for persistence issues**
  Database failures are treated as availability problems.

* **Clear failure boundaries**
  Each status code maps to a specific layer:

  * 400 → business logic
  * 422 → schema validation
  * 404 → missing resource
  * 502 → external dependency (LLM)
  * 503 → infrastructure (database)
  * 500 → internal application
