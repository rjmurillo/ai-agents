# Verdict Token Standards

**Statement**: Use structured verdict tokens for automation: PASS, WARN, CRITICAL_FAIL

**Context**: AI review workflows that need machine-readable results

**Evidence**: Enables automated CI pass/fail decisions

**Atomicity**: 94%

**Impact**: 9/10

## Token Meanings

| Token | Meaning | CI Result |
|-------|---------|-----------|
| PASS | All checks satisfied | Success |
| WARN | Non-blocking issues | Success with warning |
| CRITICAL_FAIL | Blocking issues | Failure |

## Implementation

Prompts instruct agents to emit `VERDICT: TOKEN` format:

```markdown
Based on my analysis:

VERDICT: WARN

Findings:
- Minor style issues detected
- No security concerns
```

## Parsing Pattern

```bash
VERDICT=$(echo "$RESPONSE" | grep -oP 'VERDICT:\s*\K\w+')
```

## Related

- [workflow-authorization-testable-pattern](workflow-authorization-testable-pattern.md)
- [workflow-false-positive-verdict-parsing-2025-12-28](workflow-false-positive-verdict-parsing-2025-12-28.md)
- [workflow-false-positive-verdict-parsing-fix-2025-12-28](workflow-false-positive-verdict-parsing-fix-2025-12-28.md)
- [workflow-patterns-batch-changes-reduce-cogs](workflow-patterns-batch-changes-reduce-cogs.md)
- [workflow-patterns-composite-action](workflow-patterns-composite-action.md)
