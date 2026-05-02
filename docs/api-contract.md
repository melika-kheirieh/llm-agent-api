# API Contract — /chat

## Endpoint

**POST /chat**

---

## Request

**Content-Type:** `application/json`

```json
{
  "message": "User question"
}
````

---

## Validation Rules

* `message` is **required**
* `message` must be a **non-empty string**

### Validation behavior

* Missing `message` → **422 Unprocessable Entity** (handled by FastAPI)
* Empty `message` → **400 Bad Request** (business-level validation)

---

## Response

### Success (200 OK)

```json
{
  "response": "LLM generated answer"
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

### 502 Bad Gateway — Upstream LLM failure

Returned when the LLM provider (e.g., OpenAI or Ollama) fails.

This indicates:

* the request was valid
* the failure occurred in an external dependency

---

### 503 Service Unavailable — Persistence failure

Returned when the database is unavailable or write operations fail.

This indicates:

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

* **502 for LLM failures**
  LLM providers are treated as upstream dependencies.

* **503 for persistence issues**
  Database failures are treated as availability problems.

* **Clear failure boundaries**
  Each status code maps to a specific layer:

  * 400 → business logic
  * 422 → schema validation
  * 502 → external dependency (LLM)
  * 503 → infrastructure (database)
  * 500 → internal application
