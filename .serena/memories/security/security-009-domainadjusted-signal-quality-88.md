# Security: Domainadjusted Signal Quality 88

## Skill-Security-009: Domain-Adjusted Signal Quality (88%)

**Statement**: Security review comments from any reviewer have higher actionability than style suggestions - adjust triage priority accordingly.

**Context**: When triaging bot review comments on security-sensitive files

**Evidence**: PR #52 - CodeRabbit style suggestions ~30% actionable overall, but security suggestion on .githooks was 100% valid (TOCTOU vulnerability)

**Heuristic**:

| Comment Domain | Base Signal | Adjustment |
|----------------|-------------|------------|
| Bug report | Use base | No change |
| Style suggestion | Use base | No change |
| Security issue | +40% | Always investigate |
| .githooks file | +50% | ASSERTIVE enforcement |
| Workflow file | +30% | Check for injection |

**Triage Pattern**:

```text
1. Is comment about security? → Always investigate
2. Is file in .githooks/? → ASSERTIVE enforcement
3. Is file in .github/workflows/? → Check for injection patterns
4. Otherwise → Use base signal quality
```

**Source**: `.agents/retrospective/pr-52-symlink-retrospective.md`

## Related

- [security-001-twophase-security-review](security-001-twophase-security-review.md)
- [security-002-input-validation-first-88](security-002-input-validation-first-88.md)
- [security-002-input-validation-first](security-002-input-validation-first.md)
- [security-003-secure-error-handling-90](security-003-secure-error-handling-90.md)
- [security-003-secure-error-handling](security-003-secure-error-handling.md)
