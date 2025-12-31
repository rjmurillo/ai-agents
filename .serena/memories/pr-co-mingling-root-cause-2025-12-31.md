# PR Co-Mingling Root Cause Analysis (2025-12-31)

**Date**: 2025-12-31
**Incident**: PRs #563, #564, #565 contain changes from 6+ issues (should be separate)
**Severity**: HIGH - Second instance in 48 hours
**Status**: ROOT CAUSE IDENTIFIED

## Problem Statement

Three PRs contain co-mingled changes from multiple unrelated issues:
- PR #563 (ARM Migration): 11 files spanning Issues #197, #163, #234, #97
- PR #564 (Retry Timing): 8 files spanning Issues #163, #97, #234, #197, #551
- PR #565 (Thread Scripts): 21 files spanning Issues #97, #197, #163, #234, #551

## Root Cause

**Trust-based compliance for git operations** (no verification before commit)

Agent committed work to wrong branch (feat/97-thread-management-scripts) when working on Issue #197 (ARM migration), then created PRs from multiple branches that all contained the same base commits.

## Five Whys

1. **Why did commits go to wrong branch?** Agent didn't verify current branch before committing
2. **Why no verification?** No protocol requires `git branch --show-current` before commit
3. **Why no protocol?** SESSION-PROTOCOL.md focuses on session start/end, not mid-session git safety
4. **Why no mid-session safety?** Original design assumed agents maintain branch awareness
5. **Why assume awareness?** Trust-based compliance instead of verification-based enforcement

## Evidence (Git Reflog 2025-12-29)

```text
22:54:09 - On feat/97: commit session-164 (CORRECT)
22:55:05 - On feat/97: commit ARM changes (WRONG - should be chore/197)
22:55:40 - On chore/197: commit ARM changes (DUPLICATE)
22:56:33 - On chore/197: commit retry timing (WRONG - should be feat/163)
22:56:49 - On feat/163: cherry-pick retry (PARTIAL FIX)
23:05:56 - On feat/97: commit thread scripts (CORRECT)
```

**Pattern**: 8 branch switches in 11 minutes, 2 wrong-branch commits, 1 duplicate

## Contributing Factors

1. **No pre-commit verification gate** (no `git branch --show-current` requirement)
2. **Multi-issue session** (session 97 handled 4 issues: 97, 164, 197, 163)
3. **Context switch without branch switch** (mental model diverged from git state)
4. **No pre-commit hook** (no automated branch name validation)
5. **Session log missing branch declaration** (no awareness reinforcement)

## Prevention (6 Learnings)

### 1. git-004-branch-verification-before-commit (92%)
Run `git branch --show-current` before every commit, verify output matches intended work

### 2. protocol-013-verification-over-trust-git (88%)
Use verification-based enforcement for git operations (matches Session Protocol v1.4 success)

### 3. session-scope-002-cognitive-load-risk (85%)
Limit sessions to 2 issues maximum to reduce wrong-branch commit probability

### 4. session-init-003-branch-declaration (82%)
Session logs must declare target branch in Protocol Compliance section (MUST requirement)

### 5. git-hooks-004-branch-name-validation (90%)
Pre-commit hook validates branch name contains issue number from commit message

### 6. protocol-014-trust-antipattern (94%)
Trust-based compliance fails for multi-step protocols; always use verification-based enforcement

## Systemic Pattern Discovery

**Trust-based compliance is an antipattern** across 3 documented failures:

1. **Session Protocol v1.0-v1.3**: 80% failure rate → Fixed with verification-based v1.4
2. **HANDOFF.md centralization**: 35K token bloat, 80% merge conflicts → Fixed with read-only model
3. **Git operations**: 2 incidents in 48h → Needs verification gates

**Lesson**: Any multi-step protocol using "agent should verify" instead of "agent MUST verify with tool output" will fail.

## Implementation Priority

| Priority | Action | Impact |
|----------|--------|--------|
| P0 | Add branch verification to SESSION-PROTOCOL.md | Prevents 100% of wrong-branch commits |
| P0 | Create pre-commit hook (branch validation) | Catches errors before persistence |
| P1 | Update session log template (branch declaration) | Improves branch awareness |
| P1 | Document trust antipattern in protocol guidance | Prevents future trust-based designs |
| P2 | Limit sessions to 2 issues | Reduces cognitive load |

## Related

- **Retrospective**: `.agents/retrospective/2025-12-31-pr-co-mingling-analysis.md`
- **Session Protocol**: `.agents/SESSION-PROTOCOL.md` (needs update)
- **Session Log**: `.agents/sessions/2025-12-31-session-01-pr-comingling-retrospective.md`
- **Similar Pattern**: Session Protocol v1.4 evolution (trust → verification)

## Keywords

pr-co-mingling, wrong-branch, trust-antipattern, verification-based-enforcement, git-safety, session-protocol, branch-validation, cognitive-load, multi-issue-sessions, pre-commit-hook

## Status

- [x] Root cause identified
- [x] Prevention measures defined
- [ ] SESSION-PROTOCOL.md updated (pending)
- [ ] Pre-commit hook created (pending)
- [ ] Session template updated (pending)
- [ ] Skills persisted to Serena (pending skillbook delegation)
