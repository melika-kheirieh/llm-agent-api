# Queue Lifecycle

## Flow

publish -> consume -> execute -> ack

## Failure handling

- retry transient failures
- preserve job state
- route terminal failures for review

## Boundaries

Queue infrastructure remains isolated from agent execution logic.
