# LLM Agent API

A FastAPI service that runs an async LLM agent with explicit routing, tool use, verification, and durable execution traces.

API → `AsyncAgentRuntime` → LangGraph transitions → existing router / tools / verifier / recovery → `AsyncLLMClient` → SQLite (local) or PostgreSQL (production).

This is **Agent Core v1**: a real control loop, not a chat wrapper. LangGraph owns **node transitions only**. Tools are **scope-aware** (`TrustedScope` is never model-generated). The default router is **deterministic keyword matching** (`ROUTER_MODE=keyword`). Set `ROUTER_MODE=llm` to use the LLM-backed router behind the same `Router` interface. Verification is **domain-aware** per tool, not a second model.

Why those choices: [Design Decisions](docs/DESIGN.md#design-decisions) · Demo: [docs/demo.md](docs/demo.md) · Contract: [docs/api-contract.md](docs/api-contract.md) · Database: [docs/database.md](docs/database.md)

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
  → LangGraph (route → answer | tool → verify → answer | recovery)
       Router / AgentTool / ToolVerifier / RecoveryPolicy
  → ExecutionTrace
  ↓
AsyncLLMClient (Ollama / OpenAI)
  ↓
SQLite or PostgreSQL (one transaction): chat_messages + agent_runs + agent_run_events
```

Invalid config fails **before** DB or runtime init. `POST /chat` does not return `run_id` in the JSON body; successful responses set `X-Run-Id`. Chat, run summary, and sanitized events are written together; traces are read from `GET /runs/{run_id}`.

---

## Run locally

```bash
pip install -r requirements.txt
cp .env.example .env
python -m uvicorn app.main:app --reload
```

Requires Python 3.12+ and either [Ollama](https://ollama.com) (`ollama serve && ollama pull gemma`) or an OpenAI API key. Defaults are in `.env.example`. Startup validates `LLM_PROVIDER` (`ollama` | `openai`), `ROUTER_MODE` (`keyword` | `llm`, default `keyword`), `LLM_TIMEOUT_SECONDS` (positive number), `DATABASE_URL` (non-empty), and `OPENAI_API_KEY` when the provider is OpenAI. Schema is applied with Alembic on startup. Local default is SQLite; see [docs/database.md](docs/database.md).

---

## Usage

**DIRECT** (LLM):

```bash
curl -s -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Explain what an API is in one sentence"}'
```

**Tool** (keyword route → in-process `work_order_lookup`):

Send demo scope headers. They are **not** authentication. The API copies `X-Tenant-Id` / `X-Property-Id` onto backend `TrustedScope`. The message cannot create scope. Missing headers still fail closed.

```bash
curl -sD - -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -H "X-Tenant-Id: tenant-a" \
  -H "X-Property-Id: prop-1" \
  -d '{"message":"Check work order WO-123"}'
```

```
HTTP/1.1 200 OK
X-Run-Id: …
```

```json
{"response": "Work order WO-123 is open (plumbing)."}
```

Without those headers, the same message returns `"The request could not be verified."`

Messages containing `"policy"` take `maintenance_policy_lookup`. `"work order"` / `"maintenance"` take `work_order_lookup`. Missing IDs, cross-tenant hits, missing scope, and stale policies return `"The request could not be verified."`

**Trace** — `run_id` is not in the chat body. Copy `X-Run-Id` from the chat response, then:

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

No real LLM. HTTP tests override the agent with FastAPI DI (`FakeAgent`). Router, tools, recovery, traces, and evaluation run against `AsyncAgentRuntime` with a fake `AsyncLLMClient`. Routing comparison scores keyword vs LLM trajectories, not answer text. Postgres persistence tests run only when `TEST_POSTGRES_URL` is set.

---

## What this project is NOT

Deferred on purpose (docs only, no placeholder modules):

- conversation memory persisted across processes
- checkpoints
- specialists and `DELEGATE`
- distributed workers / RabbitMQ
- RAG / LangChain chains / embeddings / vector databases
- LangGraph checkpoints, multi-agent workflows, or durable graph memory
- authentication / streaming / UI

Rationale is in [Design Decisions](docs/DESIGN.md#design-decisions).

---

## Docker

The LLM runtime stays **outside** the containers. The API image `HEALTHCHECK` uses `/health` (liveness), not `/ready`. `/ready` still checks the database.

**SQLite (single container):**

```bash
docker build -t llm-agent-api .
docker run --rm -p 8000:8000 \
  -e LLM_PROVIDER=ollama \
  -e OLLAMA_BASE_URL=http://host.docker.internal:11434 \
  -e OLLAMA_MODEL=gemma \
  -e DATABASE_URL=sqlite+aiosqlite:///./app.db \
  llm-agent-api
```

**PostgreSQL (API + database):**

```bash
docker compose up --build
```

Compose waits until Postgres is healthy, then starts the API. The API runs Alembic on boot. Data is stored in the `pgdata` volume. The Compose credentials (`agent` / `agent`) are **local development only**. Multi-replica production should run migrations as a separate step before starting API processes. Override LLM settings with a `.env` file or `-e` as usual.

License: [MIT](LICENSE)
