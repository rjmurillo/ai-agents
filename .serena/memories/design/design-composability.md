# Skill-Design-004: Composability

**Statement**: Agents should work in sequences without tight coupling

**Context**: Multi-agent workflows and handoffs

**Evidence**: Workflow skills demonstrate pipeline success with loosely coupled agents

**Atomicity**: 88%

**Impact**: 8/10

## Detection

Hard-coded agent names in outputs

## Fix

Use handoff protocol with generic references

## Good Pattern

```markdown
**Handoff to**: Next appropriate agent per orchestrator routing
**Context**: Analysis complete, implementation ready
```

## Anti-Pattern

```markdown
**Handoff to**: implementer
**Then**: qa
**Finally**: retrospective
```

Tight coupling breaks when agent names change or workflow varies.

## Related

- [design-008-semantic-precision](design-008-semantic-precision.md)
- [design-approaches-detailed](design-approaches-detailed.md)
- [design-by-contract](design-by-contract.md)
- [design-diagrams](design-diagrams.md)
- [design-entry-criteria](design-entry-criteria.md)
