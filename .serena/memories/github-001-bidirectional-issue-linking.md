# Skill-GitHub-001: Bidirectional Issue Linking

**Statement**: Link related issues by posting cross-reference comments on each, not just one

**Context**: When issues share root cause or dependencies

**Trigger**: After discovering related issues during RCA or planning

**Evidence**: Session 04 - Posted comments on #357, #338, #358 creating bidirectional navigation

**Atomicity**: 88%

**Tag**: helpful

**Impact**: 7/10

**Created**: 2025-12-24

**Validated**: 1

**Category**: GitHub

## Pattern

### Single-Direction (Anti-pattern)

```bash
# Only links FROM issue A TO issue B
gh issue comment 357 --body "Related to #338"
# Issue #338 has no reference back to #357
```

Result: One-way navigation, easy to miss relationships.

### Bidirectional (Correct Pattern)

```bash
# Link FROM #357 TO #338
gh issue comment 357 --body "Depends on #338 (retry logic prerequisite)"

# Link FROM #338 TO #357
gh issue comment 338 --body "Referenced by #357 (aggregation improvements)"

# Link FROM #357 TO #358
gh issue comment 357 --body "Related to #358 (same root cause)"

# Link FROM #358 TO #357
gh issue comment 358 --body "Related to #357 (same root cause)"
```

Result: Two-way navigation from any issue.

## Why This Matters

**GitHub Behavior**:
- Mentioning #123 in issue #456 creates link FROM 456 TO 123
- GitHub does NOT automatically create reverse link
- Issue #123 timeline shows mention but no prominent cross-reference

**Discovery Problem**:
- Developer viewing #338 won't see #357 dependency without explicit comment
- Searching within #338 won't find related work

**Solution**:
- Post comment on BOTH issues
- Creates bidirectional navigation
- Ensures discovery from either entry point

## Example: Session 04

```text
Issue #357: Aggregation failures
Issue #338: Retry logic implementation
Issue #358: Context-aware review

Comments Posted:
- #357: "Depends on #338, related to #358"
- #338: "Referenced by #357 (aggregation fix)"
- #358: "Related to #357 (same root cause)"
```

Navigation:
- User viewing #357 sees #338, #358
- User viewing #338 sees #357
- User viewing #358 sees #357

## When to Apply

AFTER:
- skill-analysis-003-related-issue-discovery (found related issues)
- RCA identifies dependencies or common root cause
- Planning reveals implementation order

BEFORE:
- Starting implementation
- Creating PR (reference all linked issues)

## Template Comments

### Dependency
```text
Depends on #{issue-number}: {brief description}
Must be completed before this issue can be fully resolved.
```

### Related (Same Root Cause)
```text
Related to #{issue-number}: {brief description}
Both issues stem from {root cause}.
```

### Blocked By
```text
Blocked by #{issue-number}: {brief description}
Cannot proceed until prerequisite is resolved.
```

### Supersedes
```text
Supersedes #{issue-number}: {brief description}
This issue provides more comprehensive solution.
```

## Success Criteria

- All related issues have cross-reference comments
- Navigation works in both directions
- Relationship type clearly stated (depends, related, blocks)
- No orphaned references

## Related Skills

- skill-analysis-003-related-issue-discovery: Finding related issues
- github-issue-assignment: Claiming discovered issues
- github-cli-issue-operations: Technical commands
