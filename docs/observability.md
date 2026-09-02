# Agent Observability

## Execution Trace

The runtime records a trace for each agent execution:

- run id
- request id
- thread id
- selected tool
- verification result
- retry count
- failure class
- terminal status

## Reliability Signals

The observability layer exposes boundaries for tracking:

- successful runs
- retries
- escalations
- failures
- execution duration

## Design Notes

Observability stays framework-agnostic. External monitoring systems can be integrated later without changing the agent core.