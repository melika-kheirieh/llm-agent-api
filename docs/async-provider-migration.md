# Async Provider Migration

Completed. The live boundary is `AsyncLLMClient`; Ollama and OpenAI implement it. `AsyncAgentRuntime` owns timeout and cancellation for the run.

## Non-goals (still deferred)

- RabbitMQ workers
- Distributed execution
- Queue lifecycle

Those layers should build on top of the current in-process async runtime, not replace it.
