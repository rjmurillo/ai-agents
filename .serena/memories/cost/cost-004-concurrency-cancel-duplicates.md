# Skill-Cost-004: Concurrency Cancels Duplicates

**Statement**: Use concurrency to cancel duplicate workflow runs on same branch

**Context**: When writing GitHub Actions workflows that may receive rapid pushes

**Action Pattern**:
- SHOULD add `concurrency:` block with workflow+ref grouping
- SHOULD set `cancel-in-progress: true`
- MUST use pattern: `${{ github.workflow }}-${{ github.ref }}`

**Trigger Condition**:
- Workflow runs on branches with frequent force-pushes
- PR receives multiple commits in quick succession

**Evidence**:
- COST-GOVERNANCE.md lines 114-122
- ADR optimization table line 84

**Quantified Savings**:
- 10-20% reduction in redundant runs
- Prevents wasted runner time on superseded commits
- For 50 runs/month with 5 duplicates: 50 → 45 runs
- At $0.05/run (10 min): $2.50/month → $2.25/month

**RFC 2119 Level**: SHOULD (COST-GOVERNANCE line 19)

## BOUNDARY: never apply this to a post-merge verifier on the default branch

Added 2026-08-03 after this pattern caused a repo-wide outage. The savings above
are real for PR and feature-branch runs. The pattern is **wrong** for any run
whose job is to witness a commit on `main`, and the `MUST` above is too strong.

`${{ github.workflow }}-${{ github.ref }}` collapses to the constant
`<workflow>-refs/heads/main` for every merge, so all merges share one group.
Setting `cancel-in-progress: false` does **not** save you: a concurrency group
holds at most one pending run, and an arriving run evicts the pending one
regardless. Measured 2026-08-02: 19 consecutive pushes to `main` cancelled in 45
seconds, one survivor, zero jobs created on any of the 19. Across nine workflows
in this repo, 25 to 43 percent of main pushes never ran at all.

Discriminator: **is losing this run acceptable?** For a superseded PR commit,
yes, that is the whole point. For the run that verifies a commit already on
`main`, no, there is no later run that covers it.

Correct shape when a workflow serves both roles:

```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}-${{ github.ref == 'refs/heads/main' && github.sha || 'shared' }}
  cancel-in-progress: ${{ github.ref != 'refs/heads/main' }}
```

Main gets one group per commit so nothing can be evicted; PR and branch runs end
in the constant `shared` and keep the savings quantified above.

See `ci/ci-concurrency-group-evicts-pending-runs-on-main.md` for the full
mechanism, and issues #4350 and #4176.

**Atomicity**: 97%

**Tag**: helpful

**Impact**: 7/10

**Created**: 2025-12-20

**Validated**: 1 (COST-GOVERNANCE policy)

**Category**: CI/CD Cost Optimization

**Pattern**:
```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```

**Use Case**: Particularly valuable for:
- Long-running test suites
- Build workflows on active PR branches
- Workflows triggered by every commit
