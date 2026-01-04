# API Contract — /chat

## Endpoint

POST /chat

---

## Request Body

Content-Type: `application/json`

```json
{
  "message": "User question"
}
````

### Validation

* `message` is **required**
* `message` must be a **non-empty string**
* Empty or missing `message` is rejected

---

## Successful Response

```json
{
  "response": "LLM generated answer"
}
```

---

## Error Responses

### 400 Bad Request (validation)

Returned when `message` is missing or empty.

```json
{
  "detail": "message is required"
}
```

### 502 Bad Gateway (LLM provider failure)

Returned when the upstream LLM call fails.

### 503 Service Unavailable (persistence failure)

Returned when the database is unavailable or persistence fails.

### 500 Internal Server Error

Returned for unexpected internal errors.

---

## Notes

* `400` is intentionally used for input validation (instead of FastAPI default `422`)
* `502` distinguishes upstream LLM failures from internal application errors
* The contract is designed to remain stable as tools or memory are added
