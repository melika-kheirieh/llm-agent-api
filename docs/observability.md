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

HTTP request logs also record `path`, `method`, `status`, and `latency_ms`. LLM failure logs include `failure_class` (`model_timeout` or `model_error`). Persistence failure logs include `failure_class=persistence_failure`.

`failure_class` values: `model_timeout`, `tool_timeout`, `model_error`, `tool_error`, `verification_failure`, `persistence_failure`, `cancelled`, `unknown`. Successful runs leave it `null`. `recovery_decision` and `retry_count` are on the in-memory trace and in `chat_success` logs; `recovery_decision` is not a database column.

Thread-scoped context is not implemented. Trace objects may carry a `thread_id` of `None`; it is not persisted.

## Reliability Signals

The runtime already encodes:

- successful DIRECT and tool runs (`outcome=success`)
- bounded retries (`retry_count`, `recovery_decision`)
- domain verification failure (`failure_class=verification_failure`)
- tool timeout vs model timeout (`tool_timeout` vs `model_timeout`)
- upstream model timeout/errors (`502`)

No separate metrics collector or tracing vendor is wired.

## Design Notes

Observability stays framework-agnostic. External monitoring can be added later without changing the agent loop.
