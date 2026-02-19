# Backpressure Pattern

**Category**: Distributed Systems, Resilience
**Source**: `.agents/analysis/advanced-engineering-knowledge.md`

## Core Concept

Throttle upstream producers when downstream consumers are overwhelmed.

## Problem Without Backpressure

Unbounded queues grow until memory exhaustion. System crashes.

## Strategies

| Strategy | Description | Trade-off |
|----------|-------------|-----------|
| Blocking | Producer waits | High latency |
| Dropping | Discard excess messages | Data loss |
| Buffering | Bounded queue | Memory limit |
| Signaling | Tell producer to slow down | Requires protocol support |

## Implementation Patterns

- **Reactive Streams**: Publisher/Subscriber with demand signaling
- **Rate limiting**: Token bucket, leaky bucket algorithms
- **Load shedding**: Reject requests above capacity
- **Throttling**: Queue depth triggers slowing

## Application

Use backpressure when:
- Processing can't keep up with input rate
- Memory growth indicates unbounded queues
- System instability under load

## Related

- [resilience-patterns](resilience-patterns.md) - Fault tolerance
- [cap-theorem](cap-theorem.md) - Distributed systems trade-offs
