# Skill-Analysis-003: Git Blame Root Cause Investigation

**Statement**: Use `git blame` → `git show commit` → `gh pr view` workflow to trace code changes to originating PR and context.

**Context**: When investigating bugs, regressions, or unexpected behavior.

**Evidence**: Session 56: Traced Import-Module bug from failing line → commit 981ebf7 → PR #212 → identified security remediation context.

**Atomicity**: 92%

**Impact**: 9/10 - Essential for understanding code history and intent

## Pattern

```bash
# Step 1: Identify the commit that introduced the line
git blame path/to/file.ps1 | grep "Import-Module"
# Output: 981ebf7 (Author 2025-12-21) Import-Module .github/scripts/...

# Step 2: View the full commit with context
git show 981ebf7

# Step 3: Find the PR that introduced the commit
gh pr list --search "981ebf7" --state all
# OR extract PR number from commit message
git show 981ebf7 | grep -oP '#\K\d+'

# Step 4: View PR for full context
gh pr view 212

# Step 5: Understand the "why" - read PR description
gh pr view 212 --json body --jq '.body'
```

## Why It Matters

- Avoid re-introducing previous bugs
- Understand trade-offs and constraints
- Identify if fix was incomplete or introduced regression
- Preserve security fixes while correcting bugs

## Anti-Pattern

Fixing bugs without understanding original context - may revert security fixes or reintroduce previous bugs.

## Related

- [analysis-001-comprehensive-analysis-standard](analysis-001-comprehensive-analysis-standard.md)
- [analysis-002-rca-before-implementation](analysis-002-rca-before-implementation.md)
- [analysis-003-related-issue-discovery](analysis-003-related-issue-discovery.md)
- [analysis-004-verify-codebase-state](analysis-004-verify-codebase-state.md)
- [analysis-comprehensive-standard](analysis-comprehensive-standard.md)
