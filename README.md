# LLM Agent API

A FastAPI service that runs an async LLM agent with explicit routing, tool execution, verification, and persisted execution traces.

Designed as a **reviewer-friendly backend**:
API → AsyncAgentRuntime → AsyncLLMClient (provider-agnostic) → Persistence.

---

## Quick Demo

See a 30–60 second demo flow here: [docs/demo.md](docs/demo.md)

---

## Why this project exists

Most LLM demos are simple wrappers around an API call.

This project focuses on **structure and boundaries**, not feature breadth.

The goal is to demonstrate how to design a backend for LLM-based applications where:
- the API layer is independent of the model provider
- agent orchestration is isolated and testable
- routing, tools, verification, and recovery are explicit
- execution traces are durable and queryable

This is Agent Core v1: a foundation, not a feature-complete agent platform.

---

## Features

- FastAPI `POST /chat` and `GET /runs/{run_id}`
- `AsyncAgentRuntime` as the execution source of truth
- Deterministic router (`DIRECT` or `USE_TOOL`)
- Async tool execution with verification and bounded recovery
- Pluggable LLM providers:
  - **Ollama** (local, no API key, no cost)
  - **OpenAI** (optional, env-driven; supports custom base URL)
- SQLite persistence: chat history (`chat_messages`) and agent runs (`agent_runs`)
- Evaluation cases that run against the same runtime wiring
- Lightweight observability (structured logs, HTTP latency, execution traces)
- Design rationale: [docs/DESIGN.md](docs/DESIGN.md)

---

## Architecture at a glance

```
Client
  ↓
FastAPI (POST /chat)
  ↓
AsyncAgentRuntime
  ↓
AgentRouter  →  DIRECT  →  AsyncLLMClient (Ollama / OpenAI)
             →  USE_TOOL →  tool → Observation → ToolVerifier → RecoveryPolicy
  ↓
ExecutionTrace
  ↓
Persistence (SQLite: chat_messages + agent_runs)
```

Each layer has a single responsibility and can be tested independently.

HTTP `POST /chat` still returns only `{"response": "..."}`. Run metadata is persisted separately and read via `GET /runs/{run_id}`.

---

## Requirements

- Python 3.12+
- Either:
  - Ollama (local LLM runtime), or
  - OpenAI API key

---

## Run the service (TL;DR)

```bash
pip install -r requirements.txt
cp .env.example .env
python -m uvicorn app.main:app --reload
```

Server will be available at:

[http://127.0.0.1:8000](http://127.0.0.1:8000)

---

## Setup

### 1) Ollama (local)

```bash
ollama serve
ollama pull gemma
```

---

### 2) Environment variables

```bash
cp .env.example .env
```

#### Option A: Ollama (local)

```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=gemma
DATABASE_URL=sqlite+aiosqlite:///./app.db
```

#### Option B: OpenAI (cloud)

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
# OPENAI_BASE_URL=https://api.openai.com/v1
DATABASE_URL=sqlite+aiosqlite:///./app.db
```

---

## Usage

### Chat endpoint

```bash
curl -i -X POST "http://127.0.0.1:8000/chat" \
  -H "Content-Type: application/json" \
  -d '{"message":"Say a short sentence in English."}'
```

Successful response:

```json
{
  "response": "..."
}
```

Tool-backed example:

```bash
curl -i -X POST "http://127.0.0.1:8000/chat" \
  -H "Content-Type: application/json" \
  -d '{"message":"Check work order WO-123"}'
```

### Run lookup

After a chat request succeeds, the execution trace is stored under `run_id` and can be fetched:

```bash
curl -i "http://127.0.0.1:8000/runs/<run_id>"
```

Unknown `run_id` returns **404**.

---

### Validation behavior

* Missing `message` → **422 Unprocessable Entity** (FastAPI validation)
* Empty `message` → **400 Bad Request**

```json
{
  "detail": "message is required"
}
```

---

## API Contract

[docs/api-contract.md](docs/api-contract.md)

---

## Database

* SQLite database: `app.db` (async driver: `sqlite+aiosqlite`)
* Table: `chat_messages` — user message and assistant response
* Table: `agent_runs` — execution traces keyed by `run_id`

---

## Testing

Tests are written using `pytest` and run **without a real LLM**.

* HTTP tests override the agent dependency with a fake runtime
* Runtime tests drive `AsyncAgentRuntime` with fake LLM/tool implementations
* Evaluation cases use the same container wiring as production (`build_runtime`)

```bash
pytest -q
```

---

## Observability (Minimal)

* Structured JSON logs
* Request latency logging (`latency_ms`)
* Execution traces (logged on chat success, persisted on `agent_runs`)

Details: [docs/observability.md](docs/observability.md)

---

## What this project is NOT

This project intentionally does NOT include:

* conversation memory or thread context
* checkpoints
* specialists or `DELEGATE` routing
* RabbitMQ, workers, or distributed execution
* RAG or vector databases
* LangChain / LangGraph
* authentication / multi-user support
* streaming responses
* UI layer

These are valid later milestones. They are documented as non-goals in [docs/adr/001-v1-architecture-boundaries.md](docs/adr/001-v1-architecture-boundaries.md), not as empty modules.

---

## Running with Docker (API only)

The FastAPI service runs in Docker.
The LLM runtime runs **outside** the container.

### Build

```bash
docker build -t llm-agent-api .
```

### Run (Ollama)

```bash
docker run --rm -p 8000:8000 \
  -e LLM_PROVIDER=ollama \
  -e OLLAMA_BASE_URL=http://host.docker.internal:11434 \
  -e OLLAMA_MODEL=gemma \
  -e DATABASE_URL=sqlite+aiosqlite:///./app.db \
  llm-agent-api
```

### Run (OpenAI)

```bash
docker run --rm -p 8000:8000 \
  -e LLM_PROVIDER=openai \
  -e OPENAI_API_KEY="sk-..." \
  -e OPENAI_MODEL="gpt-4o-mini" \
  -e DATABASE_URL=sqlite+aiosqlite:///./app.db \
  llm-agent-api
```

---

## Status

Agent Core v1 is a **reviewable async agent backend**: routing, tools, verification, bounded recovery, evaluation, and persisted traces — without pretending unimplemented layers exist.
