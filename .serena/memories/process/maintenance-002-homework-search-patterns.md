# Maintenance: Homework Search Patterns

## Skill-Maintenance-002: Homework Search Patterns

**Statement**: Search merged PRs for 'Deferred to follow-up', 'TODO', 'future improvement' to find homework items

**Context**: When scanning for deferred work in merged PRs to create tracking issues

**Evidence**: Session 39 (2025-12-20) - Scanned 27 PRs using these patterns and found 5 actionable homework items:
- Issue #144: Eliminate path list duplication in pester-tests.yml
- Issue #145: Fix duplicate job names in pester-tests.yml
- Issue #146: Convert skip-tests XML generation from bash to PowerShell
- Issue #149: Pre-commit hook should validate staged content
- Issue #150: Extract duplicated verdict evaluation logic

**Search Patterns**:
- "Deferred to follow-up"
- "future improvement"
- "A future improvement could be"
- "TODO" (in review comments, not code)
- "follow-up task"
- "out of scope for this PR"
- "addressed in a future PR"

**False Positives to Filter**:
- Generic "TODO" in bot failure messages (not actionable)
- Nitpick comments already addressed in follow-up commits
- "should be" suggestions in passing reviews (not homework)

**Atomicity**: 92%

**Source**: Session 38 retrospective (2025-12-20)

**Related Skills**: Skill-Maintenance-003

---