# Skill-Architecture-002: Model Selection by Complexity

**Statement**: Match AI model tier to task complexity for cost efficiency

**Context**: Agent configuration and resource optimization

**Evidence**: ADR-002 model selection optimization

**Atomicity**: 85%

**Impact**: 7/10

## Model Tiers

| Tier | Use Cases |
|------|-----------|
| **Opus** | Complex reasoning, architecture, security |
| **Sonnet** | Balanced tasks, implementation, QA |
| **Haiku** | Simple/fast, formatting, simple queries |

**Benefit**: Cost reduction while maintaining quality

**Source**: `.agents/architecture/ADR-002-agent-model-selection-optimization.md`

## Related

- [architecture-003-dry-exception-deployment](architecture-003-dry-exception-deployment.md)
- [architecture-015-deployment-path-validation](architecture-015-deployment-path-validation.md)
- [architecture-016-adr-number-check](architecture-016-adr-number-check.md)
- [architecture-adr-compliance-documentation](architecture-adr-compliance-documentation.md)
- [architecture-composite-action](architecture-composite-action.md)
