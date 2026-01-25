# Critique and Escalation Protocol

**Statement**: When specialists disagree, document positions and escalate to high-level-advisor

**Context**: Multi-agent decision conflicts and disagreements

**Evidence**: Agent templating critique identified specialist disagreement pattern

**Atomicity**: 90%

**Impact**: 8/10

## Escalation Protocol

1. Document each specialist's position clearly
2. Note areas of agreement vs. disagreement
3. Identify decision criteria that differ
4. Escalate to high-level-advisor with all positions
5. Apply disagree-and-commit after decision

## Anti-Patterns

- Stalling on consensus
- Overriding specialist without escalation
- Endless debate without resolution

## Documentation Format

```markdown
## Specialist Disagreement

### Position A (architect)
[Position summary]

### Position B (implementer)
[Position summary]

### Agreed Points
- [Common ground]

### Contested Points
- [Where they differ]

### Recommended Escalation
high-level-advisor with context: [summary]
```

## Related

- [quality-agent-remediation](quality-agent-remediation.md)
- [quality-basic-testing](quality-basic-testing.md)
- [quality-definition-of-done](quality-definition-of-done.md)
- [quality-prompt-engineering-gates](quality-prompt-engineering-gates.md)
- [quality-qa-routing](quality-qa-routing.md)
