# Skill-Validation-005: PR Feedback Gate

**Statement**: PR feedback from automated reviewers (Copilot, CodeRabbit, Gemini, cursor, GitHub Security) constitutes validation evidence that must be addressed before claiming completion.

**Context**: Any PR with automated review comments

**Atomicity**: 92%

## Comment Triage Requirements

| Action | Description |
|--------|-------------|
| **Addressed** | Code changed to fix issue |
| **Acknowledged** | Valid but deferred (documented reason) |
| **Dismissed** | False positive (with evidence) |
| **Blocked** | High/Critical security = merge blocker |

## Reviewer Signal Quality

| Reviewer | Signal Rate | Priority |
|----------|-------------|----------|
| cursor[bot] | 100% | P0 - Process immediately |
| GitHub Security | ~95% | P0 - Security blocking |
| Copilot | ~44% | P2 - Review carefully |
| CodeRabbit | ~50% | P2 - Check for duplicates |

## Evidence

- PR #60: 30 comments ignored when claiming "zero bugs"
- Pattern: Copilot flagged command injection risks (eval with user input)
- Pattern: GitHub Security flagged code injection vulnerabilities
