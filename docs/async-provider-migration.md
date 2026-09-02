# Async Provider Migration

Completed. The live boundary is `AsyncLLMClient`; Ollama and OpenAI implement `generate` and `generate_structured`. Structured JSON/schema parse lives in the provider layer; the runtime still owns timeout and cancellation for the run.

## Non-goals (still deferred)

- RabbitMQ workers
- Distributed execution
- Queue lifecycle

Those layers should build on top of the current in-process async runtime, not replace it.
