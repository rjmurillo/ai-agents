# Security: Domainadjusted Signal Quality For Security Comment

## Skill-Security-009: Domain-Adjusted Signal Quality for Security Comments (88%)

**Statement**: Security review comments from any reviewer have higher actionability than style suggestions - adjust triage priority accordingly

**Context**: When triaging bot review comments on security-sensitive files

**Evidence**: PR #52 - CodeRabbit style suggestions ~30% actionable overall, but security suggestion on .githooks was 100% valid (TOCTOU vulnerability)

**Atomicity**: 88%

**Tag**: helpful (triage)

**Impact**: 7/10

**Heuristic**:

| Comment Domain | Base Signal | Adjustment |
|----------------|-------------|------------|
| Bug report | Use base | No change |
| Style suggestion | Use base | No change |
| Security issue | +40% | Always investigate |
| .githooks file | +50% | ASSERTIVE ENFORCEMENT required |

**Source**: `.agents/retrospective/pr-52-symlink-retrospective.md`

---

## Related

- [security-001-twophase-security-review](security-001-twophase-security-review.md)
- [security-002-input-validation-first-88](security-002-input-validation-first-88.md)
- [security-002-input-validation-first](security-002-input-validation-first.md)
- [security-003-secure-error-handling-90](security-003-secure-error-handling-90.md)
- [security-003-secure-error-handling](security-003-secure-error-handling.md)
