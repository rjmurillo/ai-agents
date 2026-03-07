# Expand and Contract Pattern

**Category**: Migration Patterns
**Source**: Martin Fowler

## Core Concept

Safe schema and API changes over time through parallel deployment.

## Process

1. **Expand**: Add new fields/endpoints, support both old and new
2. **Migrate**: Move clients to new version
3. **Contract**: Deprecate and remove old version

## Key Insight

Never make breaking changes atomically. Always have a period of parallel support.

## Example: API Field Rename

```text
Phase 1 (Expand): 
  - Add new field "customer_id"
  - Keep old field "user_id"
  - Both return same value

Phase 2 (Migrate):
  - Clients switch to "customer_id"
  - Monitor usage of "user_id"

Phase 3 (Contract):
  - Remove "user_id" when usage is zero
```

## Application

- Database schema migrations without downtime
- API versioning for breaking changes
- Configuration format updates
- Data model evolution

## Anti-Pattern

Big-bang migrations that require coordinated deployment of all consumers.

## Related

- [strangler-fig-pattern](strangler-fig-pattern.md): Incrementally replace legacy systems
- [feature-toggles](feature-toggles.md): Decouple deploy from release
- `backward-compatibility`: Support older clients
