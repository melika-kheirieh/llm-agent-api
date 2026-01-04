# LLM Agent API

A minimal FastAPI service that runs an LLM-based agent and stores chat history.

Designed as a **clean, extensible, reviewer-friendly skeleton**:
API → Agent → LLM (provider-agnostic) → Persistence, with lightweight observability.

---

## Features

- FastAPI `POST /chat` endpoint
- Minimal Agent abstraction (analyze → respond)
- Pluggable LLM providers:
  - **Ollama** (local, no API key, no cost)
  - **OpenAI** (optional, env-driven; supports custom base URL)
- SQLite persistence (`message`, `response`, `timestamp`)
- Dependency-injection friendly design (testable without real LLM calls)
- Lightweight observability (structured logging + request latency)
- Design rationale: [docs/DESIGN.md](docs/DESIGN.md)

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
````

Server will be available at:

* [http://127.0.0.1:8000](http://127.0.0.1:8000)

---

## Setup

### 1) Ollama (local) — start and pull a model

```bash
ollama serve
ollama pull gemma
```

---

### 2) Environment variables

Copy `.env.example` to `.env` and adjust values as needed:

```bash
cp .env.example .env
```

#### Option A: Ollama (local)

```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=gemma
DATABASE_URL=sqlite:///./app.db
```

#### Option B: OpenAI (cloud)

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
# Optional: custom gateway (OpenRouter, proxy, etc.)
# OPENAI_BASE_URL=https://api.openai.com/v1
DATABASE_URL=sqlite:///./app.db
```

---

### 3) Install dependencies

```bash
pip install -r requirements.txt
```

---

### 4) Run the API

```bash
python -m uvicorn app.main:app --reload
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

### Validation error example

Empty or missing `message` returns **400 Bad Request**:

```json
{
  "detail": "message is required"
}
```

---

## API Contract

A concise description of the request/response behavior:

* [docs/api-contract.md](docs/api-contract.md)

---

## Database

* Chats are stored in `app.db` (SQLite)
* Table: `chat_messages`
* For inspection, you can use **DB Browser for SQLite**

---

## Testing

Tests are written using `pytest` and are designed to run **without a real LLM**.

* Agent dependency is overridden using FastAPI DI
* A `FakeAgent` simulates responses and failures
* Persistence is verified via function-level mocking

Run:

```bash
pytest -q
```

---

## Observability (Mini)

The API includes lightweight observability features:

* Structured JSON logs
* HTTP middleware for request latency logging (`latency_ms`)
* Event-style logs (success/failure markers)

This is intentionally minimal and avoids heavy tracing frameworks.

---

## Design Notes

* The API layer is **provider-agnostic**
* LLM provider selection is done via environment variables only
* Agent, persistence, and transport layers are clearly separated
* Hooks are intentionally left for future extensions:

  * Tools
  * Memory
  * RAG

---

## Running with Docker (API only)

The FastAPI service can run inside Docker.
The LLM runtime is expected to run **outside** the container
(Ollama locally, or OpenAI over the network).

### Build

```bash
docker build -t llm-agent-api .
```

### Run (Ollama on host — macOS)

```bash
docker run --rm -p 8000:8000 \
  -e LLM_PROVIDER=ollama \
  -e OLLAMA_BASE_URL=http://host.docker.internal:11434 \
  -e OLLAMA_MODEL=gemma \
  -e DATABASE_URL=sqlite:///./app.db \
  llm-agent-api
```

> macOS note: `host.docker.internal` allows the containerized API
> to access the locally running Ollama service.

### Run (OpenAI)

```bash
docker run --rm -p 8000:8000 \
  -e LLM_PROVIDER=openai \
  -e OPENAI_API_KEY="sk-..." \
  -e OPENAI_MODEL="gpt-4o-mini" \
  -e DATABASE_URL=sqlite:///./app.db \
  llm-agent-api
```

---

## Status

This project is intentionally scoped as a **clean, reviewable foundation**
rather than a feature-heavy demo.
