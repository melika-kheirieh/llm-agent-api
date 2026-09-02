# Async Provider Runtime

## Goal
Introduce the async provider execution boundary for the agent runtime.

## Scope
- Async LLM provider contract
- Provider implementation migration path
- Cancellation and timeout ownership boundary
- Testability through async provider mocks

## Design
The agent runtime depends on an async provider interface instead of a concrete client implementation.

Flow:

Request -> Async Agent Runtime -> Async Provider -> Response

This keeps orchestration independent from provider details.
