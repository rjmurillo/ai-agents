# Strangler Fig Pattern

**Category**: Migration Patterns
**Source**: `.agents/analysis/senior-engineering-knowledge.md`
**Origin**: Martin Fowler

## Core Concept

Migrate legacy systems incrementally rather than attempting big-bang rewrites.

Named after strangler fig trees that grow around host trees, eventually replacing them.

## Process

1. Identify bounded context to extract
2. Route new traffic to new system
3. Backfill data migration
4. Route existing traffic incrementally
5. Decommission old system

## Benefits

- Reduced risk (fail small, not big)
- Continuous delivery during migration
- Faster time to value
- Learn from early migrations

## Implementation Techniques

- Facade/proxy pattern to route requests
- Event sourcing to sync data
- Database views for compatibility
- API versioning for gradual migration

## Anti-Pattern

Big-bang rewrite. Almost always fails for systems of significant complexity.

## Related

- `feature-toggles` - Control traffic routing
- `branch-by-abstraction` - Safe refactoring behind interfaces
