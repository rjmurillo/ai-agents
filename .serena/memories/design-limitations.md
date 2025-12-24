# Skill-Design-003: Explicit Limitations

**Statement**: Agents must declare what they DON'T do to prevent misuse

**Context**: Agent definition and user expectations

**Evidence**: Agent interview protocol requires "What does it NOT do?" question

**Atomicity**: 88%

**Impact**: 8/10

## Detection

Missing "Constraints" section

## Fix

Document anti-patterns and explicit boundaries

## Template

```markdown
## Constraints (What This Agent Does NOT Do)

- Does not modify production databases
- Does not approve its own PRs
- Does not bypass security review for credentials
- Defers to [other-agent] for [specific-task]
```
