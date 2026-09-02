# Async Provider Migration

## Status

Complete. Live providers implement `AsyncLLMClient`. `AsyncAgentRuntime` is the only execution path.

## What landed

- Async LLM provider contract
- Ollama (`httpx`) and OpenAI (`AsyncOpenAI`) implementations
- Timeout ownership on the runtime (`LLM_TIMEOUT_SECONDS`)
- Cancellation-safe provider `generate` / `aclose`
- Provider selection remains independent from agent orchestration

## Non-goals (still deferred)

- RabbitMQ workers
- Distributed execution
- Queue lifecycle

Those layers should build on top of the stable async runtime and must not be added as empty stubs.
