# ADR 0001: Evolve V1 behind the Agent facade

- Status: Accepted
- Date: 2026-08-29

## Context

V1 is a small synchronous FastAPI service. The API depends on an `Agent` facade, while provider-specific LLM clients and persistence live behind separate boundaries.

V2 will add asynchronous I/O, typed tool contracts, a bounded agent workflow, deterministic verification, context/state handling, evaluation, and operational hardening.

Introducing LangGraph directly into the HTTP layer would couple transport code to orchestration details and make the migration harder to test incrementally.

## Decision

Keep `Agent` (or a narrowly renamed `AgentRunner`) as the application-facing orchestration facade.

The migration order is:

1. Restore and protect a green V1 baseline.
2. Make model, persistence, and HTTP I/O genuinely asynchronous.
3. Add the graph behind the facade.
4. Add tools, deterministic verification, bounded retry, state/context policy, and evaluation incrementally.

The API layer must not depend directly on LangGraph-specific state or graph objects.

Trusted authorization scope such as tenant or property identity must come from backend/API context rather than model-generated tool arguments.

## Consequences

### Positive

- V1 remains easy to reason about and recover.
- HTTP contracts can remain stable while orchestration changes.
- Graph behavior can be tested with fake models and fake tools without network access.
- Provider and orchestration implementations remain replaceable.

### Costs

- The facade adds one explicit abstraction layer.
- Some graph-native concepts must be translated at the application boundary.

## Non-goals for the baseline phase

This ADR does not introduce LangGraph, memory, tools, async persistence, or new product behavior. Those changes begin only after baseline CI is green.
