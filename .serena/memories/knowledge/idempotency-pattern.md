# Idempotency Pattern

**Category**: API Design, Distributed Systems
**Source**: `.agents/analysis/advanced-engineering-knowledge.md`

## Core Principle

An operation can be applied multiple times without changing the result beyond the initial application.

## Importance

Enables safe retries. If a request times out, clients can retry without duplicate effects.

## Examples

| Idempotent | Not Idempotent |
|------------|----------------|
| PUT /user/123 {name: "John"} | POST /users {name: "John"} |
| DELETE /user/123 | POST /orders (creates new) |
| Setting absolute value | Incrementing counter |

## Implementation Techniques

1. **Idempotency keys**: Client provides unique ID, server deduplicates
2. **Version numbers**: Reject if version mismatch
3. **State machines**: Operations valid only in certain states
4. **Natural idempotency**: Design operations to be naturally idempotent

## Database Pattern

```sql
INSERT INTO operations (idempotency_key, result)
VALUES (@key, @result)
ON CONFLICT (idempotency_key) DO NOTHING
RETURNING result;
```

## Related

- [resilience-patterns](resilience-patterns.md) - Retries need idempotency
- [cap-theorem](cap-theorem.md) - Distributed systems context
