# A Concurrency Group Evicts Pending Runs, And cancel-in-progress Does Not Stop It

**Atomicity**: 96%
**Category**: CI infrastructure, GitHub Actions semantics
**Source**: 2026-08-03 measurement. Issues #4350 and #4176.
**Tag**: harmful-if-unknown

## Symptom

A post-merge workflow on `main` shows `conclusion: cancelled` even though its
concurrency block says `cancel-in-progress: false` (or the conditional form
`${{ github.ref != 'refs/heads/main' }}`, which evaluates to `false` on main).

Nobody cancelled it. No job ever ran. `gh api .../runs/<id>/jobs` returns an
empty list, and `gh api repos/OWNER/REPO/commits/<sha>/check-runs` has **no
entry for that workflow at all**. Not failed, not skipped: absent.

## The contradiction

Reading GitHub's docs, `cancel-in-progress: false` means "runs in this group are
never cancelled." That reading is wrong, and it is wrong in the direction that
costs you a verifier.

`cancel-in-progress` governs runs that are **already running**. It says nothing
about the queue. A concurrency group holds **at most one pending run**. When a
third run arrives while one is running and one is pending, the pending one is
evicted and marked `cancelled`. `cancel-in-progress: false` does not suppress
that eviction.

Consequence: under a merge burst, **only the last push in the burst survives.**

## Evidence

`instruction-budget.yml`, whose concurrency block already read
`cancel-in-progress: ${{ github.ref != 'refs/heads/main' }}` at the time
(verified with `git show 7b5279967:.github/workflows/instruction-budget.yml`):

```
2026-08-02T21:46:20Z ev=push concl=success   head=a72ee868c
2026-08-02T21:46:18Z ev=push concl=cancelled head=8fccc019c
2026-08-02T21:46:16Z ev=push concl=cancelled head=7b5279967
... 16 more consecutive cancellations ...
2026-08-02T21:45:35Z ev=push concl=cancelled head=3a1bf9df7
```

19 consecutive cancelled pushes to `main` in 45 seconds. The eviction lands
before any job is created:

```
gh api repos/rjmurillo/ai-agents/actions/runs/30768601554
created=2026-08-02T21:45:41Z updated=2026-08-02T21:45:45Z concl=cancelled
gh api repos/rjmurillo/ai-agents/actions/runs/30768601554/jobs
(zero jobs)
```

Blast radius across `main` pushes, per workflow, cancelled out of the last 100:

| workflow | cancelled / 100 |
|---|---|
| pytest.yml | 43 |
| codeql-analysis.yml | 32 |
| cli-smoke.yml | 28 |
| instruction-budget.yml | 25 |
| passive-context-budget.yml | 25 |
| skill-passive-compliance.yml | 25 |
| skillbook-validation.yml | 25 |
| validate-generated-agents.yml | 25 |
| yaml-lint.yml | 25 |

## Why the obvious fix does not work

Issue #4176 diagnosed this class on 2026-08-01 and closed after changing
`cancel-in-progress: true` to `cancel-in-progress: ${{ github.ref != 'refs/heads/main' }}`
in six workflows. The burst above is from 2026-08-02, a day later, with that fix
already in the tree. Necessary, not sufficient.

The bug is the **group key**, not `cancel-in-progress`. Every push to main shares
`<workflow>-refs/heads/main`, so every push is evictable.

## The fix

Give main pushes a group per commit. Then there is never a second member of the
group and nothing can be evicted. Everything else keeps today's behavior.

```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}-${{ github.ref == 'refs/heads/main' && github.sha || 'shared' }}
  cancel-in-progress: ${{ github.ref != 'refs/heads/main' }}
```

- push to main: group ends in the unique commit SHA. One group per commit. Fixed.
- push to a non-main branch: group ends in `shared`, cancel-in-progress true,
  stale runs still cancel. Unchanged, still saves money.
- pull_request: group keys on the PR number, ends in `shared`, stale PR runs
  still cancel. Unchanged.

Preserve each workflow's existing group prefix. Not all use `github.workflow`:
`codeql-analysis.yml` uses a literal `codeql-analysis-`, and
`validate-generated-agents.yml` uses `validate-agents-`.

## Enumerate the class

```bash
for f in $(git ls-tree -r --name-only origin/main -- .github/workflows | grep -E '\.ya?ml$'); do
  body=$(git show "origin/main:$f"); grep -q '^concurrency:' <<<"$body" || continue
  grp=$(sed -n '/^concurrency:/,/^[a-z]/p' <<<"$body" | grep -m1 'group:'); [ -z "$grp" ] && continue
  if grep -qE 'github\.ref' <<<"$grp" && ! grep -qE 'github\.sha' <<<"$grp"; then
    grep -qE '^\s*push:' <<<"$body" && echo "  $(basename $f)"
  fi
done
```

## Measuring the cancellation rate

```bash
gh api "repos/OWNER/REPO/actions/workflows?per_page=100" --jq '.workflows[]|"\(.id)\t\(.path)"'
gh api "repos/OWNER/REPO/actions/workflows/<id>/runs?branch=main&event=push&per_page=100" \
  --jq '[.workflow_runs[]|.conclusion] | "\(length) \(map(select(.=="cancelled"))|length)"'
```

`per_page=100` on the workflows list is required. The default is 30 and this
repo has 72 workflows, so an unpaged lookup silently returns nothing for two
thirds of them and looks like a missing workflow rather than a missing page.

## The generalization

A concurrency group is a **serialization point**. Putting a post-merge verifier
in a group shared by every merge means it can only observe the tree as fast as
merges arrive, and under a burst it observes nothing. Anything whose job is to
witness every commit must be keyed per commit. Group only what you are willing
to lose.

## Boundary against the cost guidance

`cost/cost-004-concurrency-cancel-duplicates.md` says to use
`${{ github.workflow }}-${{ github.ref }}` with `cancel-in-progress: true`, and
its 10 to 20 percent savings are real. That guidance is correct for PR and
feature-branch runs and wrong for post-merge verification on the default branch.
Discriminator: **is losing this run acceptable?** For a superseded PR commit,
yes. For the only run that will ever verify a commit on `main`, no.

## Related

- `decision-a-whole-corpus-gate-cannot-be-path-filtered.md` covers the two other
  independent ways a gate on main fails to measure the tree (path-filter skip
  reporting success, and non-strict required checks admitting a union breach).
  All three were live simultaneously on 2026-08-02.
- `ci/ci-infrastructure-003-job-status-verdict-distinction.md` for the general
  rule that a run conclusion is not a verdict.
