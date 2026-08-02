# mergeStateStatus BLOCKED can be stale, reconcile against per-check state

**Category**: PR Review
**Source**: 2026-08-02 fleet session, PRs #4303, #4208, #4318

## Statement

`mergeStateStatus: BLOCKED` on a pull request is a cached verdict, not a live
one. It can report BLOCKED when every latest check is green and no threads are
unresolved. Reconcile it against per-check state before acting on it.

## Evidence

Three PRs queried in the same minute with `gh pr view N --json mergeStateStatus,statusCheckRollup,reviewThreads`.

| PR | mergeStateStatus | Latest per-check state | Reality |
|----|------------------|------------------------|---------|
| #4303 | BLOCKED | all SUCCESS, 0 unresolved threads | stale, merged cleanly as `5ee7a95d5` |
| #4208 | BLOCKED | Detect Changed Sessions FAILURE, Run Python Tests FAILURE | genuine |
| #4318 | BLOCKED | Aggregate Results FAILURE, Detect Changed Sessions FAILURE | genuine |

So the field is right two times in three and wrong once, which is the worst
possible reliability: high enough to trust by habit, low enough to burn a cycle.

## Why it costs time

Reading BLOCKED and stopping means one of two wasted paths. Either re-run a
suite that already passed, or open an issue against a workflow that is not
broken. Both take longer than the one query that settles it.

## Procedure

Reduce `statusCheckRollup` by **latest** run per check name, then judge:

```bash
gh pr view N --json statusCheckRollup \
  --jq '[.statusCheckRollup[]
         | {name: (.name // .context),
            conclusion: (.conclusion // .state),
            t: (.startedAt // .createdAt)}]
        | group_by(.name)
        | map(sort_by(.t) | last)
        | map(select(.conclusion != "SUCCESS" and .conclusion != "NEUTRAL"))'
```

Empty output plus zero unresolved threads means BLOCKED is stale.

Three traps in that reduction, all three hit while writing this memory or
earlier in the same session:

1. **Never collapse the rollup into a `{name: conclusion}` dict.** A workflow
   that runs on more than one trigger emits several rows under one name, and the
   dict silently keeps whichever arrives last. This produced a false SKIPPED
   reading on PR #4124's `Run Python Tests`, which was actually SUCCESS.
2. **Never reduce by best conclusion either.** That hides a real failure behind
   an older green run. Sort by time and take the last.
3. **`statusCheckRollup` is a union of two node types and only one of them has
   the obvious fields.** `CheckRun` carries `name`, `conclusion`, `startedAt`.
   `StatusContext` carries `context`, `state`, `createdAt` and no `conclusion`
   at all. A naive `{name, conclusion, startedAt}` projection turns every
   `StatusContext` row into all nulls, and since `null != "SUCCESS"` the filter
   then reports a phantom failing check with no name. The `//` fallbacks above
   normalize both shapes.

Trap 3 was found by running the first draft of this command against a fixture
rather than by reasoning about it. The draft looked correct and was not.

## Test provenance

The expression above was verified against a hand-built fixture covering both
node types, not against the live API, because the GraphQL quota was exhausted at
the time. Four cases: a green `StatusContext` is dropped, a red `StatusContext`
is caught, a stale `SKIPPED` superseded by a newer `SUCCESS` is dropped, and a
newer `FAILURE` superseding an older `SUCCESS` is caught. The field names come
from the GitHub GraphQL schema and from rollup payloads read earlier in the same
session, so they are confirmed by use for `CheckRun`; the `StatusContext` branch
is schema-derived and has not yet been exercised against a real payload.

## Boundary

A successful merge is not retroactive evidence the PR was mergeable. GitHub
recomputes on the merge call. Check per-check state first, then merge; do not
merge first and infer the state from the outcome.

## Related

- `pr-review/pr-status-001.md`. The agent's own status vocabulary, which derives
  BLOCKED from CI state directly. That derivation is the correct direction and
  this memory explains why the API field cannot substitute for it.

## The other BLOCKED: a required context that never reported

The stale-BLOCKED case above is a PR whose checks went green after the field was
computed. There is a second, opposite case that the same jq cannot see, and it
is the one that strands PRs indefinitely.

A PR can read `BLOCKED` with a full board of green checks and **zero failures**.
The per-check reduction returns an empty non-success list, which reads as "this
is just stale, merge it", and the merge then fails. The cause is not a red
check. It is a **required context that produced no check run at all**. An absent
context cannot appear in a rollup, so every reduction over the rollup, including
the union-safe one above, is blind to it by construction.

## Do not measure this with statusCheckRollup: it truncates

This is the trap that made my first pass at this section wrong, so it is
recorded before the result rather than after it.

`gh pr view N --json statusCheckRollup` does **not** return every check run. On
PR #4003 it returned 77 rows. The REST check-runs endpoint on the same head SHA
reported `total_count` **133**, across 86 distinct names. The rollup silently
dropped 56 runs, and the names it dropped were not random: they included the six
agent-review jobs and their aggregator.

Reducing over that truncated set produced a confident, specific, and entirely
false finding: that seven required contexts were missing on four PRs. Every one
of those seven was in fact present on the head SHA. The number 77 was real; the
population it was drawn from was not the population I claimed.

Use REST, and check the count against what you received:

```bash
S=$(gh api "repos/$O/$R/pulls/$N" --jq .head.sha)
gh api "repos/$O/$R/commits/$S/check-runs?per_page=100" --jq '.total_count'
gh api "repos/$O/$R/commits/$S/check-runs?per_page=100" \
  --jq '[.check_runs[].name]|unique[]' | sort -u > present.txt
```

If `total_count` exceeds the rows you received, paginate before concluding
anything. A check that is merely on page two is indistinguishable from a check
that never ran, and the second reading is the one that invents a blocker.

## Diagnose it by difference

The rollup tells you what ran. The block is about what did not. So compare the
two sets, taking the present set from REST:

```bash
gh api "repos/$O/$R/rules/branches/main" \
  --jq '[.[]|select(.type=="required_status_checks")
         |.parameters.required_status_checks[].context]|sort' > required.txt

while IFS= read -r r; do
  grep -Fxq "$r" present.txt || echo "MISSING: $r"
done < required.txt
```

A non-empty result names the block precisely. An empty result means the required
set did report, and the block is coming from somewhere other than status checks.

There are 17 required contexts on `main` as of 2026-08-01. `Add Bot Reviewer` is
**not** one of them, so its failure never blocks a merge. Check membership in
the required set before calling any red check a blocker.

## What the corrected measurement actually showed

Same four PRs, same day, measured through REST instead of the rollup:

| PR | distinct check names | required contexts missing |
|---|---|---|
| #4003 | 86 | `Validate PR title` |
| #3984 | 82 | none |
| #4260 | 81 | `Validate PR`, `Validate PR title` |
| #4296 | 83 | `Validate PR title` |

So the real recurring gap is one context, `Validate PR title`, not seven. Why it
did not report is **not established**; do not assert a cause without reading the
run list for the head SHA.

#3984 is the more interesting row. Nothing is failing and nothing required is
missing, yet it still reads `BLOCKED`. Status checks are only one of the
requirements in this repo's ruleset, which also demands **conversation
resolution**. A PR with unresolved review threads blocks with a clean, complete
check board. When the set difference comes back empty, look at
`reviewThreads(isResolved: false)` before assuming the field is stale.

## Why this matters more than the stale case

A stale BLOCKED resolves itself on the next recomputation. A missing required
context does not resolve at all: there is no red check to re-run, no failure to
fix, and the PR board looks green. Nothing in the UI or in `mergeStateStatus`
distinguishes the two.

`workflow_dispatch` does not fix it. A dispatched run checks out the ref you
dispatched, so its check runs attach to that SHA. Dispatching the quality gate
for PR #4003 produced run `30767761170` with `headSha` equal to `origin/main`,
not the PR head. Check runs on main cannot satisfy a requirement evaluated
against the PR's head commit. The event that re-runs a workflow against a PR
head is a push to the PR branch.
