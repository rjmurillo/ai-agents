# Security Scan Skill Observations

**Last Updated**: 2026-02-08
**Sessions Analyzed**: 1

## When to Use Security-Scan Skill (HIGH confidence, session 1187, 2026-02-08)

**Trigger**: PR review comments with CWE-* identifiers

**Pattern**: Security bots flag path traversal (CWE-22), injection (CWE-78), etc.
- Bot comments are structured and scannable
- Route to security-scan skill, NOT manual fixes
- Skill encodes validated patterns (repository line length, type conventions)

**User correction**: "just use the security-scan skill to fix these"
- Bypassed skill for manual implementation
- Led to linting iterations that skill would have avoided
- User noted: "appears the skills have no real effect here"

**Workflow**:
1. Run security-scan on files flagged by bot
2. Apply skill's recommended fixes
3. Re-run security-scan to verify (exit code 0)
4. Reply to PR comments with scan results as evidence

## Constraints (HIGH confidence)

- Always use security-scan skill when PR comments contain CWE-* patterns (Session 1187, 2026-02-08)
- Never bypass skill for manual security fixes (Session 1187, 2026-02-08)

## Preferences (MED confidence)

- Bot comments are machine-parseable and should trigger automatic skill routing (Session 1187, 2026-02-08)
- Skills encode repository-specific conventions better than pre-training (Session 1187, 2026-02-08)

## Related

- [security-001-twophase-security-review](security-001-twophase-security-review.md)
- [security-002-input-validation-first-88](security-002-input-validation-first-88.md)
- [security-002-input-validation-first](security-002-input-validation-first.md)
- [security-003-secure-error-handling-90](security-003-secure-error-handling-90.md)
- [security-003-secure-error-handling](security-003-secure-error-handling.md)
