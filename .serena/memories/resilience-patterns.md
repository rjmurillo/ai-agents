# Resilience Patterns

**Category**: Distributed Systems, Fault Tolerance
**Source**: `.agents/analysis/advanced-engineering-knowledge.md`
**Origin**: Michael Nygard's "Release It!"

## Core Patterns

### Circuit Breaker

Stops calling a failing service to prevent cascade failures.

**States**:
- **Closed**: Requests pass normally
- **Open**: Requests fail immediately (threshold breached)
- **Half-Open**: Limited requests test recovery

**Implementation**: Polly (.NET), Resilience4j (Java)

### Bulkheads

Isolate components so failure in one does not affect others.

**Types**:
- Thread pool isolation
- Connection pool isolation
- Process isolation
- Service isolation

### Retries with Backoff

Retry transient failures with increasing delays.

**Strategy**:
- Exponential backoff: 100ms, 200ms, 400ms...
- Jitter: Randomness prevents thundering herd
- Max retries: Limit total attempts
- Retry budgets: Limit per time window

### Timeouts

Every external call needs a timeout. No exceptions.

**Guidelines**:
- p99 latency + buffer
- Separate connect and read timeouts
- Consider retry budget impact

## Application

Use these patterns together for defense in depth. Failures are inevitable; design for them.

## Related

- `cap-theorem` - Distributed systems trade-offs
- `idempotency-pattern` - Safe retries
