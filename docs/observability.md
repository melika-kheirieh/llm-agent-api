# Agent Observability

## Execution Trace

After each `AsyncAgentRuntime` run, `trace_from_state()` builds an `ExecutionTrace` that is:

- logged on successful `POST /chat`
- persisted on `agent_runs`
- readable via `GET /runs/{run_id}`

Stored / returned fields:

- `run_id`
- `terminal_status`
- `decision`
- `selected_tool`
- `verification_result`
- `attempts`
- `retry_count`
- `outcome`
- `failure_class`
- `created_at` (persist time)

HTTP request logs also record `path`, `method`, `status`, and `latency_ms`.

Thread-scoped context is not implemented. Trace objects may carry a `thread_id` of `None`; it is not persisted.

## Reliability Signals

The runtime already encodes:

- successful DIRECT and tool runs (`outcome=success`)
- bounded retries (`retry_count`)
- verification failure / review (`needs_human_review`)
- upstream LLM timeout/errors (`502`)

No separate metrics collector or tracing vendor is wired.

## Design Notes

Observability stays framework-agnostic. External monitoring can be added later without changing the agent loop.
