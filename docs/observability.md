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

`router_type` (`keyword` or `llm`), `decision`, `selected_tool`, and `routing_ms` (milliseconds from `run_started` to `route_selected`) are on the in-memory `ExecutionTrace` and in `chat_success` logs. They are not persisted and are not returned by `GET /runs/{run_id}`. LLM routing is an extra model call; `routing_ms` is the in-process way to see that cost. No metrics vendor is wired.

Step events (`run_started`, `route_selected`, `tool_started`, `tool_completed`, `tool_failed`, `verification_completed`, `recovery_decision`, `run_completed`, `run_failed`) are recorded on the in-memory trace in order. Logs include `event_names` and `event_count`. Events are not persisted and are not returned by `GET /runs/{run_id}`.

Thread-scoped context is in-process only: `thread_id` is copied onto the in-memory `ExecutionTrace` and into `chat_success` logs. It is not a database column and is not returned by `GET /runs/{run_id}`. History lives in a per-runtime buffer, not in SQLite.

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
