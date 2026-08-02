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
