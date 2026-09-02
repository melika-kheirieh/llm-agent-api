# Agent Observability

## HTTP logs

Each request is logged with path, method, status, and `latency_ms`. Successful chats also log execution-trace fields (`run_id`, terminal status, decision, selected tool, verification, attempts, retry count, outcome, failure class).

## Execution Trace

`AsyncAgentRuntime.run_with_trace()` maps finished `AgentState` into an `ExecutionTrace`. After the run, the API persists that trace on `agent_runs` and exposes it at `GET /runs/{run_id}`.

Stored fields:

- run_id
- terminal_status
- decision
- selected_tool
- verification_result
- attempts
- retry_count
- outcome
- failure_class
- created_at

Thread / conversation context is not implemented. `thread_id` is not persisted.

## Design Notes

Observability stays framework-agnostic: structured logs plus a queryable SQLite table. External monitoring systems can be integrated later without changing the agent core.
