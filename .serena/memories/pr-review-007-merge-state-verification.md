# Skill-PR-Review-007: Pre-Review Merge State Verification

**Statement**: Run Test-PRMerged.ps1 before review work to prevent wasted effort on merged PRs.

**Context**: PR review workflow initialization (blocking gate)

**Evidence**: PR #345 correctly detected MERGED state via GraphQL, skipped review work (Session 85+)

**Atomicity**: 92% | **Impact**: 8/10

## Pattern

```powershell
pwsh .claude/skills/github/scripts/pr/Test-PRMerged.ps1 -PullRequest {number}
# Exit code 0 = NOT merged, proceed with review
# Exit code 1 = IS merged, skip all review work
# Exit code 2 = Error
```

## Why GraphQL

`gh pr view --json state` may return stale "OPEN" for recently merged PRs.
GraphQL `repository.pullRequest.merged` is source of truth.

## Anti-Pattern

Starting review work without merge state check wastes effort on already-merged PRs.

## Related

- **BLOCKS**: All PR review work (acknowledgment, triage, resolution)
- **ENABLES**: Efficient review workflow routing
