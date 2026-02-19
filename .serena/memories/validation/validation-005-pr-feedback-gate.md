# Validation: Pr Feedback Gate

## Skill-Validation-005: PR Feedback Gate

**Statement**: PR feedback from automated reviewers (Copilot, CodeRabbit, Gemini, cursor, GitHub Security) constitutes validation evidence that must be addressed before claiming completion

**Context**: Any PR with automated review comments

**Trigger**: Before merging PR or claiming implementation success

**Evidence**:
- PR #60: 30 comments ignored when claiming "zero bugs"
- Pattern: Copilot flagged command injection risks (eval with user input)
- Pattern: GitHub Security flagged code injection vulnerabilities
- 4 high-severity path injection alerts require remediation

**Atomicity**: 92%

**Tag**: helpful

**Impact**: 9/10 - PR comments ARE validation data

**Comment Triage Requirements**:

| Action | Description |
|--------|-------------|
| **Addressed** | Code changed to fix issue |
| **Acknowledged** | Valid but deferred (documented reason) |
| **Dismissed** | False positive (with evidence) |
| **Blocked** | High/Critical security = merge blocker |

**Reviewer Signal Quality** (from pr-comment-responder-skills):

| Reviewer | Signal Rate | Priority |
|----------|-------------|----------|
| cursor[bot] | 100% | P0 - Process immediately |
| GitHub Security | ~95% | P0 - Security blocking |
| Copilot | ~44% | P2 - Review carefully |
| CodeRabbit | ~50% | P2 - Check for duplicates |

---

## Related

- [validation-001-validation-script-false-positives](validation-001-validation-script-false-positives.md)
- [validation-002-pedagogical-error-messages](validation-002-pedagogical-error-messages.md)
- [validation-003-preexisting-issue-triage](validation-003-preexisting-issue-triage.md)
- [validation-004-test-before-retrospective](validation-004-test-before-retrospective.md)
- [validation-006-self-report-verification](validation-006-self-report-verification.md)
