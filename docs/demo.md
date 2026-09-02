# Demo — LLM Agent API

About 60 seconds. `POST /chat` returns only `{"response": "..."}`. The trace is a separate read.

---

## 1) Start the API

```bash
pip install -r requirements.txt
cp .env.example .env
python -m uvicorn app.main:app --reload
```

[http://127.0.0.1:8000](http://127.0.0.1:8000)

Use Ollama (`ollama serve && ollama pull gemma`) or set `LLM_PROVIDER=openai` in `.env`.

---

## 2) DIRECT path (LLM)

```bash
curl -s -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Explain what an API is in one sentence"}'
```

The body is the answer only. The router did not match work-order keywords, so `AsyncAgentRuntime` called `AsyncLLMClient`.

---

## 3) Tool path (stub lookup)

```bash
curl -s -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Check work order WO-123"}'
```

```json
{"response": "Work order WO-123 is open (plumbing)."}
```

This is keyword routing plus an in-process fixture, not a live work-order system. A message like `"Need maintenance help"` (no ID) returns `"The request could not be verified."`

---

## 4) Fetch the trace

`run_id` is not in the chat JSON. After a successful `/chat`, it is:

- on the `chat_success` log line (`"run_id": "..."`)
- in SQLite `agent_runs`

```bash
sqlite3 app.db "SELECT run_id, decision, selected_tool, outcome FROM agent_runs ORDER BY created_at DESC LIMIT 1;"
```

```bash
curl -s http://127.0.0.1:8000/runs/{run_id}
```

Unknown ids return **404**.

---

## 5) Tests (no real LLM)

```bash
pytest -q
```

---

## What this demo shows

* Chat clients stay on `{ "response" }`
* DIRECT vs tool is an explicit runtime choice
* Tool success, verification failure, and traces are durable
* The loop is testable without a provider
