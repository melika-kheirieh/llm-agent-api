# Async Provider Migration

## Changes

- Add async provider boundary
- Define timeout ownership
- Prepare cancellation propagation
- Keep provider selection independent from agent orchestration

## Non-goals

- RabbitMQ workers
- Distributed execution
- Queue lifecycle

Those layers should build on top of a stable async runtime.
