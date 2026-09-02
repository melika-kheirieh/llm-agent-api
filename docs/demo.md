# Demo — LLM Agent API

This is a quick 30–60 second demo to validate the core flow of the system.

---

## 1) Start the API

```bash
uvicorn app.main:app --reload
```

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

Work-order phrasing takes the tool path instead of the LLM:

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Check work order WO-123"}'
```

---

## 3) Validate persistence

Successful chats write two SQLite tables in `app.db`:

* `chat_messages` — user message and agent response
* `agent_runs` — execution trace (`run_id`, decision, tool, verification, outcome)

Inspect with any SQLite client, or query a trace:

```bash
curl http://127.0.0.1:8000/runs/{run_id}
```

---

## 4) Run tests (no real LLM required)

```bash
pytest -q
```

Notes:

* Tests do not call a real LLM
* HTTP tests override the agent with FastAPI DI
* Runtime and evaluation tests exercise `AsyncAgentRuntime` with a fake LLM

---

## What this demo shows

* `POST /chat` is functional and still returns `{ "response": "..." }`
* `AsyncAgentRuntime` routes `DIRECT` vs tool execution
* Tool results are verified; failures can retry once then go to review
* Chat rows and execution traces are persisted
* `GET /runs/{run_id}` loads a stored trace
* The system is testable without external dependencies
