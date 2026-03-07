# Skill: Share Cache Across Git Worktrees

**Skill ID**: skill-serena-011-cache-worktree-sharing
**Category**: Setup
**Impact**: Medium (avoids redundant indexing)
**Status**: Recommended for worktree workflows

## Trigger Condition

When creating git worktree for parallel branch work.

## Action Pattern

After creating worktree, copy cache from original:

```bash
# Create worktree
git worktree add ../feature-branch feature-branch

# Copy cache to avoid re-indexing
cp -r .serena/cache ../feature-branch/.serena/cache
```

## Cost Benefit

Avoids redundant indexing time (minutes to hours on large codebases) and enables immediate symbol lookup.

## Evidence

From SERENA-BEST-PRACTICES.md lines 396-405:
- Git worktrees share codebase but have separate .serena directories
- Copying cache avoids redundant indexing
- Immediate symbol lookup available

## Example

```bash
# Original project at /project
# Create worktree at /project-feature

git worktree add ../project-feature feature-branch
cp -r /project/.serena/cache /project-feature/.serena/cache

# Now Serena in worktree has immediate index access
```

## Atomicity Score

100% - Single concept: copy cache to worktree

## Validation Count

0 (newly extracted)

## Related Skills

- skill-serena-006-pre-index-projects
