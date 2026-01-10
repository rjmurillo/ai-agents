# Historical Reference Protocol Compliance Plan

**Created**: 2026-01-01
**Issue**: Protocol compliance audit per `.agents/governance/historical-reference-protocol.md`
**Status**: In Progress

## Scope

Audit MUST-comply directories for historical reference protocol violations:

- `.agents/architecture/` (ADRs)
- `.agents/sessions/` (Session logs)
- `.serena/memories/` (Serena memories)
- `.agents/analysis/` (Analysis docs)
- `.agents/planning/` (Planning docs)
- `.agents/retrospective/` (Retrospectives)

## Protocol Requirements

Per `.agents/governance/historical-reference-protocol.md`:

| Element | Required | Format |
|---------|----------|--------|
| **Date** | MUST | `YYYY-MM-DD` |
| **Git Commit SHA** | MUST | Short or full SHA |
| **GitHub Issue** | MUST (if applicable) | `#NNN (YYYY-MM-DD)` |
| **GitHub PR** | SHOULD (if applicable) | `PR #NNN (YYYY-MM-DD)` |

## Anti-Patterns Searched

- "was done previously" without commit SHA
- "See ADR-XXX for details" without commit/date/issue
- "The original implementation..." without commit reference
- "As decided in the issue" without issue number
- "Per our previous discussion" without PR reference

## Findings

### High-Priority Violations (MUST fix)

| File | Line | Violation | Fix |
|------|------|-----------|-----|
| `.agents/analysis/003-quality-gate-comment-caching-rca.md` | 361 | Commit ref without date | Add `(2025-12-20)` to commit 911cfd0 |
| `.agents/analysis/003-quality-gate-comment-caching-rca.md` | 372 | PR ref without date | Add `(2025-12-26)` to PR #438 |
| `.agents/analysis/003-quality-gate-comment-caching-rca.md` | 382-385 | Issue/PR refs without dates | Add dates to Issue #357, #328, #329, PR #438 |

### Medium-Priority Violations (SHOULD fix)

| File | Line | Violation | Fix |
|------|------|-----------|-----|
| `.agents/analysis/281-similar-pr-detection-review.md` | 83 | PR ref without date | Add `(2025-12-22)` to PR #249 |
| `.agents/analysis/281-similar-pr-detection-review.md` | 85-86 | Issue ref without date | Add `(2025-12-22)` to Issue #244 |

### False Positives (No Fix Needed)

| File | Reason |
|------|--------|
| `.agents/retrospective/PR-52-review-issues.md` | Has session date (2025-12-17) in header; internal references are in context |
| `.agents/governance/historical-reference-protocol.md` | Contains anti-pattern examples (documentation, not violations) |
| `.agents/architecture/ADR-022-*` | Contains template placeholders, not actual references |
| Session logs (my session) | I listed anti-patterns as task description, not violations |

## Implementation Plan

1. Fix `.agents/analysis/003-quality-gate-comment-caching-rca.md`
2. Fix `.agents/analysis/281-similar-pr-detection-review.md`
3. Lint check
4. Commit changes
5. Open PR

## Data Sources

| Reference | Date | Source |
|-----------|------|--------|
| Commit 911cfd0 | 2025-12-20 | `git log --format="%ad" --date=short 911cfd0` |
| PR #249 | 2025-12-22 | `gh pr view 249 --json createdAt` |
| Issue #244 | 2025-12-22 | `gh issue view 244 --json createdAt` |
| Issue #357 | 2025-12-24 | `gh issue view 357 --json createdAt` |
| Issue #328 | 2025-12-24 | `gh issue view 328 --json createdAt` |
| Issue #329 | 2025-12-24 | `gh issue view 329 --json createdAt` |
| PR #438 | 2025-12-26 | `gh pr view 438 --json createdAt` |
