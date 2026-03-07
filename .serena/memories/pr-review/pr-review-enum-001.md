# PR Enumeration Verification Gate

**Atomicity**: 92%
**Category**: PR Review
**Source**: 2025-12-24 Parallel PR Review Retrospective

## Statement

Cross-check `gh pr list` output against all open PRs to verify completeness before processing.

## Context

After enumerating PRs for review but before starting processing. Required when processing multiple PRs in batch or parallel.

## Evidence

2025-12-24 Parallel PR Review: PR #336 missed in initial enumeration (12.5% failure rate). User intervention required: "Why do you keep missing PR 336?" Verification gate would have caught this before processing began.

## Pattern

```bash
# 1. Run gh pr list with review filters
FILTERED=$(gh pr list --json number -q 'length')

# 2. Get total open PRs (no filters)
TOTAL=$(gh pr list --state open --json number -q 'length')

# 3. Compare counts
if [ "$FILTERED" -ne "$TOTAL" ]; then
  echo "WARNING: $((TOTAL - FILTERED)) PRs filtered out"
  gh pr list --state open --json number,title
fi

# 4. Proceed only after verification passes
```

## Anti-Pattern

Assuming `gh pr list` output is complete without verification causes systematic detection failures (12.5% miss rate observed).

## Related

- [pr-156-review-findings](pr-156-review-findings.md)
- [pr-320c2b3-refactoring-analysis](pr-320c2b3-refactoring-analysis.md)
- [pr-52-retrospective-learnings](pr-52-retrospective-learnings.md)
- [pr-52-symlink-retrospective](pr-52-symlink-retrospective.md)
- [pr-753-remediation-learnings](pr-753-remediation-learnings.md)
