# Requirement Count Verification Gate

**Statement**: Implementation complete requires both tests passing AND requirement count verified (N implemented = N specified)

**Context**: Before marking any multi-item implementation as complete

**Evidence**: 4 of 20 items missed in personality integration without count verification (20% miss rate)

**Atomicity**: 93%

**Impact**: 10/10 (CRITICAL - prevents all gap scenarios)

## DoD Addition

```markdown
## Definition of Done

### Requirement Verification ← REQUIRED (NEW)
- [ ] Requirement count verified: N implemented = N specified
- [ ] Checkbox manifest 100% checked (if applicable)
- [ ] No items deferred without explicit acknowledgment
```

## Verification Pattern

1. Count items in specification/PRD
2. Count implemented items
3. Compare: `implemented == specified`
4. If mismatch, identify gaps before marking complete

## Example

| Requirement | Count |
|-------------|-------|
| Specified | 20 |
| Implemented | 16 |
| **Gap** | 4 |

Status: **INCOMPLETE** - 4 items missing

## Anti-Pattern

Marking complete based on "feels done" without counting.

## Related

- [quality-agent-remediation](quality-agent-remediation.md)
- [quality-basic-testing](quality-basic-testing.md)
- [quality-critique-escalation](quality-critique-escalation.md)
- [quality-definition-of-done](quality-definition-of-done.md)
- [quality-prompt-engineering-gates](quality-prompt-engineering-gates.md)
