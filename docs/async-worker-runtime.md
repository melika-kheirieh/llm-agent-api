# Async Worker Runtime

## Flow

request -> publisher -> queue -> worker -> agent runtime -> ack/nack

## Guarantees

- explicit job lifecycle
- retry boundary
- terminal failure handling
- broker isolation

## Worker responsibilities

- consume messages
- execute agent jobs
- report outcome
- acknowledge successful work
