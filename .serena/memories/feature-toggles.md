# Feature Toggles

**Category**: Deployment Practices
**Source**: `.agents/analysis/senior-engineering-knowledge.md`

## Purpose

Decouple deployment from release. Deploy code, enable features separately.

## Toggle Types

| Type | Lifespan | Use Case |
|------|----------|----------|
| Release | Days to weeks | Gradual rollout |
| Experiment | Days to weeks | A/B testing |
| Ops | Months | Circuit breakers, kill switches |
| Permission | Long-term | Premium features |

## Implementation Guidance

- Toggle at the edge, not deep in code
- Clean up toggles after full rollout (tech debt)
- Test both paths in CI/CD
- Maintain toggle inventory
- Consider feature flag services (LaunchDarkly, Split.io)

## Benefits

- Safer deploys (can disable without rollback)
- Gradual rollout (canary deployments)
- Experimentation (A/B testing)
- Quick incident response (kill switches)

## Anti-Pattern

Deep toggle placement creates spaghetti code. Toggle at the entry point.

## Related

- [strangler-fig-pattern](strangler-fig-pattern.md) - Incremental migration
- `branch-by-abstraction` - Safe refactoring
