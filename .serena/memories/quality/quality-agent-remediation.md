# Skill-Quality-004: Agent Remediation Requirements

**Statement**: MUST remediate agent findings based on priority and verdict levels

**Context**: After agent consultation produces findings

**Evidence**: Pattern discovered 2025-12-26, prevents ignored recommendations

**Atomicity**: 92% | **Impact**: 9/10

## Pattern

### Priority-Based Triage

| Priority | RFC 2119 | Action |
|----------|----------|--------|
| P0 / BLOCKING | MUST | Fix before proceeding |
| P1 / HIGH | SHOULD | Fix before merge |
| P2+ / MEDIUM/LOW | MAY | Fix in follow-up PR |

### Verdict-Based Actions

| Verdict | Action |
|---------|--------|
| CRITICAL_FAIL | MUST remediate - blocks merge |
| FAIL | MUST remediate - blocks merge |
| WARN | SHOULD review - proceed with caution |
| PASS | No action required |

### Evidence Documentation

When remediating, document in session log or PR:

1. **Original Finding**: Agent name, priority, description
2. **Fix Applied**: Commit SHA or explanation
3. **Verification**: Confirmation fix addresses concern

Example:

```markdown
## Remediation

- **Finding**: [security] P0 - Missing input validation on user input
- **Fix**: Added regex validation in commit abc123
- **Verification**: Re-ran security agent, now PASS
```

## Anti-Pattern

- Ignoring agent recommendations without explicit justification
- Marking P0 items as "will fix later"
- Proceeding after CRITICAL_FAIL without remediation
- Running agents but not reading their output

## Related

- [quality-basic-testing](quality-basic-testing.md)
- [quality-critique-escalation](quality-critique-escalation.md)
- [quality-definition-of-done](quality-definition-of-done.md)
- [quality-prompt-engineering-gates](quality-prompt-engineering-gates.md)
- [quality-qa-routing](quality-qa-routing.md)
