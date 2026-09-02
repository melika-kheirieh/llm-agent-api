# ADR 001: V1 Architecture Boundaries

## Status
Accepted

## Context

The project starts as a small LLM-backed FastAPI service. The first version should prioritize clear boundaries, testability, and predictable behavior before introducing more advanced agent workflows.

## Decision

V1 keeps the following boundaries:

- API layer handles HTTP concerns and request validation.
- Agent layer owns application-level orchestration.
- LLM providers are accessed through an abstraction instead of being coupled to the API.
- Persistence remains isolated behind a database layer.

## Non-goals for V1

The following are intentionally deferred:

- RAG and vector databases
- complex memory systems
- multi-step agent workflows
- streaming responses
- production authentication

## Consequences

The design keeps the current system easy to test and provides stable boundaries for future async execution, tools, evaluation, and agent workflows.
