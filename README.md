# LLM Agent API

A FastAPI service that runs an async LLM agent with explicit routing, tool use, verification, and durable execution traces.

API → `AsyncAgentRuntime` → `AsyncLLMClient` → SQLite.

This is **Agent Core v1**: a real control loop, not a chat wrapper. The router is **deterministic keyword matching** (not an LLM planner). The registered tool is an **in-process stub**. Verification is **domain-aware** (required fields, requested-id match, allowed status), not a second model.

Why those choices: [Design Decisions](docs/DESIGN.md#design-decisions) · Demo: [docs/demo.md](docs/demo.md) · Contract: [docs/api-contract.md](docs/api-contract.md)

---

## Architecture

```
Client
  ↓
FastAPI
  POST /chat          → {"response": "..."} only
  GET  /runs/{run_id} → persisted ExecutionTrace
  GET  /health        → process liveness
  GET  /ready         → database SELECT 1
  ↓
AsyncAgentRuntime
  → AgentRouter (DIRECT | USE_TOOL)
  → tool + Observation + ToolVerifier
  → RecoveryPolicy (max 2 attempts)
  → ExecutionTrace
  ↓
AsyncLLMClient (Ollama / OpenAI)
  ↓
SQLite (one transaction): chat_messages + agent_runs
```

Invalid config fails **before** DB or runtime init. `POST /chat` does not return `run_id`. Chat and trace are written together; traces are read from `GET /runs/{run_id}`.

---

## Run locally

```bash
pip install -r requirements.txt
cp .env.example .env
python -m uvicorn app.main:app --reload
```

Requires Python 3.12+ and either [Ollama](https://ollama.com) (`ollama serve && ollama pull gemma`) or an OpenAI API key. Defaults are in `.env.example`. Startup validates `LLM_PROVIDER` (`ollama` | `openai`), `LLM_TIMEOUT_SECONDS` (positive number), and `OPENAI_API_KEY` when the provider is OpenAI.

---

## Usage

**DIRECT** (LLM):

```bash
curl -s -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Explain what an API is in one sentence"}'
```

**Tool** (keyword route → stub `work_order_lookup`):

```bash
curl -s -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Check work order WO-123"}'
```

```json
{"response": "Work order WO-123 is open (plumbing)."}
```

Messages containing `"work order"` or `"maintenance"` take the tool path. Missing IDs fail verification and return `"The request could not be verified."`

**Trace** — `run_id` is not in the chat body. Read it from the latest `agent_runs` row or from the `chat_success` JSON log, then:

```bash
curl -s http://127.0.0.1:8000/runs/{run_id}
```

**Health**

```bash
curl -s http://127.0.0.1:8000/health
curl -s http://127.0.0.1:8000/ready
```

Empty `message` → **400**. Missing field → **422**. Unknown run → **404**. Model failure or model timeout → **502**. Database failure (including `/ready`) → **503**. Tool timeout returns the review message (`200`), not `502`.

---

## Testing

```bash
pytest -q
```

No real LLM. HTTP tests override the agent with FastAPI DI (`FakeAgent`). Router, tools, recovery, traces, and evaluation run against `AsyncAgentRuntime` with a fake `AsyncLLMClient`.

---

## What this project is NOT

Deferred on purpose (docs only, no placeholder modules):

- conversation memory / thread context
- checkpoints
- specialists and `DELEGATE`
- distributed workers / RabbitMQ
- RAG / LangChain / LangGraph
- authentication / streaming / UI

Rationale is in [Design Decisions](docs/DESIGN.md#design-decisions).

---

## Docker (API only)

The LLM runtime stays **outside** the container. The image `HEALTHCHECK` uses `/health` (liveness), not `/ready`.

```bash
docker build -t llm-agent-api .
docker run --rm -p 8000:8000 \
  -e LLM_PROVIDER=ollama \
  -e OLLAMA_BASE_URL=http://host.docker.internal:11434 \
  -e OLLAMA_MODEL=gemma \
  -e DATABASE_URL=sqlite+aiosqlite:///./app.db \
  llm-agent-api
```

License: [MIT](LICENSE)
