# Skill-Design-002: Clear Entry Criteria

**Statement**: Agents need explicit conditions for when to invoke them

**Context**: Agent definition and routing

**Evidence**: Vague routing caused orchestrator ambiguity in multi-agent workflows

**Atomicity**: 90%

**Impact**: 8/10

## Detection

Vague "use when" statements

## Fix

Add concrete trigger scenarios with examples

## Good Example

```markdown
## When to Use
- PR has 10+ review comments from bots
- User explicitly requests "/pr-review 123"
- Orchestrator routes PR feedback tasks
```

## Bad Example

```markdown
## When to Use
- General PR work
- Code review tasks
```

## Related

- [design-008-semantic-precision](design-008-semantic-precision.md)
- [design-approaches-detailed](design-approaches-detailed.md)
- [design-by-contract](design-by-contract.md)
- [design-composability](design-composability.md)
- [design-diagrams](design-diagrams.md)
