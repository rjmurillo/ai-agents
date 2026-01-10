# Fallacies of Distributed Computing

**Category**: Distributed Systems
**Source**: `.agents/analysis/senior-engineering-knowledge.md`
**Origin**: Peter Deutsch and others at Sun Microsystems

## The Eight Fallacies

Assumptions that cause distributed system failures:

1. The network is reliable
2. Latency is zero
3. Bandwidth is infinite
4. The network is secure
5. Topology doesn't change
6. There is one administrator
7. Transport cost is zero
8. The network is homogeneous

## Practical Implications

- Build with timeouts on every external call
- Implement retries with exponential backoff and jitter
- Use circuit breakers for failing dependencies
- Include tracing/correlation IDs for debugging
- Plan for partial failures

## Defense Patterns

| Fallacy | Defense |
|---------|---------|
| Network unreliable | Circuit breakers, retries, fallbacks |
| Non-zero latency | Timeouts, async operations, caching |
| Bandwidth limits | Pagination, compression, batching |
| Network insecure | TLS, authentication, encryption |

## Related

- `resilience-patterns` - Circuit breaker, bulkhead, retry
- `cap-theorem` - Consistency vs availability tradeoff
