# LLM Agent API

A minimal FastAPI service that runs an LLM-based agent and stores chat history.

Designed as a **clean, extensible, reviewer-friendly skeleton**:
API → Agent → LLM (provider-agnostic) → Persistence, with lightweight observability.

---

## Quick Demo

See a 30–60 second demo flow here:  
👉 [docs/demo.md](docs/demo.md)

---

## Why this project exists

Most LLM demos are simple wrappers around an API call.

This project focuses on **structure and boundaries**, not feature breadth.

The goal is to demonstrate how to design a backend for LLM-based applications where:
- the API layer is independent of the model provider
- the agent logic is isolated and testable
- external dependencies (LLMs) are clearly separated from core logic

This is a foundation, not a feature-complete agent system.

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

## Architecture at a glance

Client  
  ↓  
FastAPI (/chat)  
  ↓  
Agent (application logic)  
  ↓  
LLMClient (interface)  
  ↓  
Provider (Ollama / OpenAI)  
  ↓  
Persistence (SQLite)  

Each layer has a single responsibility and can be tested independently.

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
DATABASE_URL=sqlite:///./app.db
```

#### Option B: OpenAI (cloud)

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
# OPENAI_BASE_URL=https://api.openai.com/v1
DATABASE_URL=sqlite:///./app.db
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

👉 [docs/api-contract.md](docs/api-contract.md)

---

## Database

* SQLite database: `app.db`
* Table: `chat_messages`

---

## Testing

Tests are written using `pytest` and run **without a real LLM**.

* Agent dependency is overridden using FastAPI DI
* A `FakeAgent` simulates responses and failures
* Persistence is verified via mocking

```bash
pytest -q
```

---

## Observability (Minimal)

* Structured JSON logs
* Request latency logging (`latency_ms`)
* Success/failure markers

---

## What this project is NOT

This project intentionally does NOT include:

* RAG (retrieval-augmented generation)
* vector databases
* authentication / multi-user support
* streaming responses
* complex memory systems
* UI layer

These are valid extensions, but are excluded to keep the project:

* simple
* testable
* easy to review

The focus is on correctness, structure, and clean design.

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
  -e DATABASE_URL=sqlite:///./app.db \
  llm-agent-api
```

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
