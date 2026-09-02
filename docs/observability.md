# Agent Observability

## Execution Trace

After each `AsyncAgentRuntime` run, `trace_from_state()` builds an `ExecutionTrace` that is:

- logged on successful `POST /chat`
- persisted on `agent_runs` (summary) and `agent_run_events` (sanitized steps)
- advertised to operators as the `X-Run-Id` response header on successful `POST /chat` (not in the JSON body)
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
- `events` (ordered sanitized step events)

HTTP request logs also record `path`, `method`, `status`, and `latency_ms`. LLM failure logs include `failure_class` (`model_timeout` or `model_error`). Persistence failure logs include `failure_class=persistence_failure`.

`failure_class` values: `model_timeout`, `tool_timeout`, `model_error`, `tool_error`, `verification_failure`, `persistence_failure`, `cancelled`, `unknown`. Successful runs leave it `null`. `recovery_decision`, `retry_count`, and `error_code` are on the in-memory trace and in `chat_success` logs; they are not `agent_runs` columns. `error_code` is a tool token (`cross_tenant`, `wrong_property`, `tool_timeout`, `not_found`, …), not a tenant or property id. Domain/security rejections stay `failure_class=tool_error` and are distinguished from timeouts by `failure_class=tool_timeout` and/or `error_code`. Failed tool events persist that token as `metadata.error`.

`router_type` (`keyword` or `llm`), `decision`, `selected_tool`, and `routing_ms` (milliseconds from `run_started` to `route_selected`) are on the in-memory `ExecutionTrace` and in `chat_success` logs. `router_type` and `routing_ms` are not `agent_runs` columns. `routing_ms` is not returned by `GET /runs/{run_id}`. LLM routing is an extra model call; `routing_ms` is the in-process way to see that cost. No metrics vendor is wired.

Step events (`run_started`, `route_selected`, `tool_started`, `tool_completed`, `tool_failed`, `verification_completed`, `recovery_decision`, `run_completed`, `run_failed`) are recorded on `AgentState` in order, then persisted on `agent_run_events` with the run. Failed tool events may include an `error` code (`not_found`, `cross_tenant`, `wrong_property`, `missing_policy`, …). Persisted metadata is allowlisted: no `tenant_id`, `property_id`, tool payloads, or prompts. `GET /runs/{run_id}` returns those sanitized events. Logs still include `event_names` and `event_count`.

Thread-scoped context is in-process only: `thread_id` is copied onto the in-memory `ExecutionTrace` and into `chat_success` logs. It is not a database column and is not returned by `GET /runs/{run_id}`. History lives in a per-runtime buffer, not in SQLite.

There are three separate data surfaces:

- **AgentState** — internal debug: raw observations, TrustedScope, unsanitized in-memory events
- **Persisted operator trace** — `agent_runs` summary plus sanitized `agent_run_events`
- **Model-facing context** — `ToolEvidence` after verification, without tenant/property

## Reliability Signals

The runtime already encodes:

- successful DIRECT and tool runs (`outcome=success`)
- bounded retries (`retry_count`, `recovery_decision`)
- domain verification failure (`failure_class=verification_failure`)
- tool timeout vs model timeout (`tool_timeout` vs `model_timeout`)
- domain/security tool rejection vs operational tool failure (`error_code` on in-memory traces; same `failure_class=tool_error` except timeouts)
- upstream model timeout/errors (`502`)

No separate metrics collector or tracing vendor is wired.

## Design Notes

Observability stays framework-agnostic. Step events are recorded on `AgentState` the same way as before the LangGraph migration. Tracing does not depend on LangGraph internals. External monitoring can be added later without changing the agent loop.
