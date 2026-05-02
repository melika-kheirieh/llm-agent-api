# Demo — LLM Agent API

This is a quick 30–60 second demo to validate the core flow of the system.

---

## 1) Start the API

```bash
uvicorn app.main:app --reload
````

The service will be available at:

[http://127.0.0.1:8000](http://127.0.0.1:8000)

---

## 2) Send a request

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Explain what an API is in one sentence"}'
```

Example response:

```json
{
  "response": "An API is a way for software systems to communicate with each other."
}
```

---

## 3) Validate persistence

The interaction is stored in SQLite:

* File: `app.db`
* Table: `chat_messages`

You can inspect it using any SQLite client (e.g., DB Browser for SQLite).

---

## 4) Run tests (no real LLM required)

```bash
pytest -q
```

Notes:

* Tests do not call a real LLM
* The agent dependency is overridden using FastAPI DI
* A `FakeAgent` simulates responses and failures

---

## What this demo shows

* The `/chat` endpoint is functional
* The agent pipeline (analyze → respond) is executed
* LLM providers are abstracted behind an interface
* Responses are persisted
* The system is testable without external dependencies
