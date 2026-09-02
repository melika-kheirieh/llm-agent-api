# RabbitMQ Execution Flow

## Overview

This document describes the broker integration boundary for async agent execution.

Flow:

request -> publisher -> queue -> worker -> agent runtime -> ack/nack

## Delivery semantics

- Acknowledgement happens only after successful execution.
- Retryable failures are requeued according to retry policy.
- Terminal failures move to failure handling.

## Isolation

The agent core remains independent from broker implementation details.
