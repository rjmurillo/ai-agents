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

## The rollup truncates, so do not reduce over it

This is the most expensive trap in this file, because it manufactures findings
that look precise. It cost me two false conclusions in a row on the same PR.

`gh pr view N --json statusCheckRollup` does **not** return every check run. On
PR #4003 it returned 77 rows. The REST check-runs endpoint on the same head SHA
reports `total_count` **133**, across 103 distinct names. The rollup dropped 56
runs, and the names it dropped were not a random sample: they included the six
agent-review jobs and their aggregator.

Reducing over that truncated set produced a confident, specific, false finding:
that seven required contexts had never reported on four PRs. Every one of the
seven was present on every head SHA.

The second attempt used REST, which is the right endpoint, with `per_page=100`
against a `total_count` of 133. That returned the first page only and produced a
second false finding: that `Validate PR title` was missing. The workflow run
list showed it had completed successfully on that exact SHA. It was on page two.

Both errors have the same shape. A number was attached to a population that was
never checked. Absence in a truncated list is indistinguishable from absence in
the repository, and only one of those two readings invents a blocker.

Always paginate, and always reconcile the count you received against the count
the API reports:

```bash
S=$(gh api "repos/$O/$R/pulls/$N" --jq .head.sha)
gh api "repos/$O/$R/commits/$S/check-runs?per_page=100" --jq '.total_count'
gh api --paginate "repos/$O/$R/commits/$S/check-runs?per_page=100" \
  --jq '.check_runs[]|{name,status,conclusion,started_at}' > runs.jsonl
wc -l < runs.jsonl   # must equal total_count
```

## The correct per-check reduction

Take the latest run per name, then compare against the required set. Presence is
not success: a required context that reported and failed blocks just as hard as
one that never reported, and a presence-only check will miss it.

```bash
jq -s 'group_by(.name)|map(sort_by(.started_at)|last)' runs.jsonl > latest.json
gh api "repos/$O/$R/rules/branches/main" \
  --jq '[.[]|select(.type=="required_status_checks")
         |.parameters.required_status_checks[].context]|sort' > required.txt

while IFS= read -r r; do
  v=$(jq -r --arg n "$r" '.[]|select(.name==$n)|.conclusion' latest.json)
  [ "$v" = "success" ] || [ "$v" = "skipped" ] || echo "BLOCKER: $r = ${v:-ABSENT}"
done < required.txt
```

There are 17 required contexts on `main` as of 2026-08-01. `Add Bot Reviewer` is
**not** one of them, so its failure never blocks a merge. Check membership in the
required set before calling any red check a blocker.

## What the corrected measurement showed

PR #4003, measured with pagination on 2026-08-02:

| Signal | Value |
|---|---|
| check runs on head SHA | 133 rows, 103 distinct names |
| required contexts absent | none |
| required contexts not `success` | none, all 17 `completed/success` |
| review threads | 5 total, **0 unresolved** |
| `mergeable` | `MERGEABLE` |
| `mergeStateStatus` | **`BLOCKED`** |

Nothing failing, nothing missing, nothing unresolved, and still `BLOCKED`. That
is this memory's original thesis, reached the hard way: the field is stale. It
is not evidence of a second failure mode, and I should not have proposed one
before the population was verified.

Approvals are not the explanation either. `reviewDecision` reads null or `none`
on these PRs, and it reads the same on PRs that have already merged, so it is
not the gate. A field that reads identically on merged and open PRs cannot be
what distinguishes them.

## workflow_dispatch cannot clear a check requirement

A dispatched run checks out the ref you dispatched, so its check runs attach to
that SHA. Dispatching the AI quality gate for PR #4003 produced run
`30767761170` with `headSha` equal to `origin/main`, not the PR head. Check runs
on main cannot satisfy a requirement evaluated against the PR's head commit. The
event that re-runs a workflow against a PR head is a push to the PR branch.

## The merge call is the authoritative test, and it is safe to make

The instinct is to establish mergeability first and merge second. For this field
that instinct is backwards, and acting on it is what strands PRs.

`mergeStateStatus` is a cached advisory value. The merge endpoint is not: it
evaluates the ruleset server-side at the moment of the call and returns 405 with
the specific unmet requirement when one exists. Protection cannot be bypassed by
attempting a merge, so an attempt costs one API call and either succeeds or
tells you the real reason it cannot.

That makes the attempt strictly more informative than the field it replaces.

Confirmed on 2026-08-02. Four PRs read `BLOCKED` with no failing check. After
the paginated measurement on #4003 showed all 17 required contexts green and 0
unresolved threads, all four were merged on the first attempt with no
intervention:

| PR | squash commit |
|---|---|
| #4003 | `dcf10ea275c9` |
| #3984 | `e452ba71e432` |
| #4260 | `80ca5e383451` |
| #4296 | `13a9a1d4600f` |

Four for four. `BLOCKED` was stale in every case.

This does not soften the boundary recorded above. A merge that succeeds still
does not prove the PR was mergeable at some earlier moment, because GitHub
recomputes on the call. The two statements answer different questions. "Was it
mergeable an hour ago" is not answerable from the outcome. "Is it mergeable now"
is answerable only by making the call.

So the rule is: do not treat `BLOCKED` as a stop. Measure the required contexts
with pagination, check for unresolved threads, and if both come back clean,
attempt the merge and read the refusal if one comes. Skipping the attempt on the
strength of a cached field is how a green, fully reviewed PR sits open for days.
