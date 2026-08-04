# Decision: read PR check status by head SHA, never from `gh pr checks`

## Question

How do you find out whether a pull request is actually failing CI?

## Conventional answer

`gh pr checks <number>`. It is the purpose-built subcommand, it prints a clean
table of check names and conclusions, and it exits non-zero when something failed.

## First-principles position

It reports check runs from superseded commits as current failures. The output is
a view over every check run associated with the pull request, not over the check
runs of the commit that is actually up for merge. Push a fix and the old failing
run stays in the table beside the new passing one.

The question you care about is a property of a commit, not of a pull request, so
ask it of the commit.

## Evidence

Measured 2026-08-02 on PR #4233.

```
$ gh pr checks 4233
Validate Spec Coverage   fail   2m4s   https://github.com/.../runs/...
```

The same check, queried against the pull request's real head SHA:

```
$ gh pr view 4233 --json headRefOid -q .headRefOid
ccdf4d371d...
$ gh api "repos/rjmurillo/ai-agents/commits/ccdf4d371d.../check-runs?per_page=100" --paginate \
    --jq '.check_runs[] | select(.name=="Validate Spec Coverage") | .conclusion'
success
```

The failing run had judged an older revision of the PR body. Re-measuring all 16
mergeable PRs this way changed the assessment of several of them, and this
subcommand alone sent me chasing two failures that did not exist.

Same class as issue #3978, which records GraphQL `statusCheckRollup` retaining
superseded runs. Two surfaces, one root cause: check runs are retained per pull
request, and neither surface filters to the head commit.

## Decision

Resolve the head SHA first, then read that commit's check runs:

```bash
PR=4233
SHA=$(gh pr view "$PR" --json headRefOid -q .headRefOid)
gh api "repos/rjmurillo/ai-agents/commits/$SHA/check-runs?per_page=100" --paginate \
  --jq '.check_runs[] | select(.conclusion=="failure") | .name'
```

Empty output means nothing is failing on the commit under consideration. Check for
`.status=="in_progress"` separately; a run that has not finished is not a pass.

That snippet is a first approximation. It selects a failure anywhere on the
commit, which over-reports once a context has been re-run. See the 2026-08-04
amendment at the end of this file for the correct reduction.

This applies to any automation that gates on CI state, and to every manual triage
of a red pull request. Treat a `gh pr checks` failure as a hypothesis to confirm
against the head SHA, never as a finding.

## Correction, 2026-08-04: the blanket "never `gh pr checks`" was too strong

The reasoning above is sound about superseded runs. The prescription that
followed from it is not, and following it cost three false "no failing checks"
readings in one session.

`gh pr checks <n> --json name,state,bucket` paginates internally. A hand-rolled
GraphQL reduction does not. Measured on this repo: one head SHA carries **131
check contexts** (two triggers times roughly 65 jobs), so a
`contexts(last:60)` selection silently drops rows. On PRs 4402, 4525, and 4531
that window returned no failing rows while the server's own
`statusCheckRollup.state` said `FAILURE`. The dropped row was `Validate PR` on
all three. Even `first:100` truncates here.

Two rules follow, and they outrank the "resolve the head SHA first" recipe above
whenever they conflict with it:

1. **Ask the server for the aggregate; do not rebuild it.**
   `statusCheckRollup.state` is the authoritative verdict. Any local reduction,
   including the REST recipe above, is a hypothesis about that verdict.
2. **Compare any window to `totalCount` before filtering it.** REST exposes
   `total_count`; GraphQL exposes `totalCount`. A filter that returns nothing
   over a truncated window is indistinguishable from a filter that returns
   nothing over a complete one, and it announces no loss.

The head-SHA point survives: superseded runs are real. Get both properties by
letting a paginating client do the reading, then cross-checking the count.

```bash
gh pr checks "$PR" --json name,state,bucket \
  --jq '.[] | select(.bucket=="fail") | .name'
```

Validated against a known answer: this found `Validate PR` on 4402 across 116
rows, the row the 60-wide window had dropped.

The two amendments below were measured independently on other pull requests.
They reach the same conclusion by a different route and give a cheaper form of
it: ask the server for `statusCheckRollup.state` instead of listing rows at all.
Use the rollup first. Fall back to the paginating `gh pr checks` listing above
only once the rollup says `FAILURE` and you need to know which row.

## Amendment 2026-08-04: reduce to the latest run per name, and count skipped as passing

Measured on PR #4539 (head `8aed3408f`), which carried 153 check runs on one
commit. Three further traps sit on top of the head-SHA rule. Each produced a
wrong answer here before it was measured.

**1. `per_page=100` without `--paginate` truncates silently.** The un-paginated
query returned 100 of 153 runs. It dropped a successful `Validate Plugin Version
Bump` and made a green required check look unsatisfied, which cost an
investigation into that workflow's path filter for a job that had already
passed. Confirm the population before trusting the reduction:

```bash
gh api "repos/rjmurillo/ai-agents/commits/$SHA/check-runs?per_page=1" --jq .total_count
```

**2. GitHub decides a required context by the latest run bearing that name, not
by any run.** Both obvious reductions are wrong, in opposite directions:

- Selecting `.conclusion=="failure"` anywhere on the commit, which is what the
  Decision snippet above does, reports a failure that a later successful re-run
  has already replaced.
- Reducing to a `{name: conclusion}` dict discards a real success when two
  workflows emit the same context name. PR #4124 carried two `Aggregate Results`
  rows, one success and one failure.

Reduce by `(started_at, id)` per name and read only the winner. On #4539 the
"any success" reduction reported zero unsatisfied required checks while the
newest `Aggregate Results` run was red, and that run was the actual reason the
PR would not merge.

**3. `skipped` and `neutral` satisfy a required context.** A required check whose
job is gated by a path filter reports `skipped`, and GitHub counts that as
passing. Treating "not success" as red disagreed with the server's own `clean`
on PR #4542. The passing set is `{success, skipped, neutral}`.

**The server stays the authority.** When a local reduction disagrees with
`mergeable_state`, the reduction is wrong. A `blocked` state with every required
check green means the cause is outside check runs: an unresolved review thread,
a required context that never reported at all, or a legacy commit status, which
lives at `/commits/{sha}/status` and is a separate surface from `/check-runs`.

## Amendment 2026-08-04b: do not reduce at all, ask the server for the aggregate

The amendment above prescribes a local reduction. Measured on PR #4515, that
reduction returns the wrong answer, so the runnable form below is the one to
copy.

**4. Two concurrent runs under different triggers share one required name, and
neither supersedes the other.** `.github/workflows/pytest.yml` runs on both
`push` and `pull_request`. One head SHA therefore produces two rows named `Run
Python Tests`, a required context, from two runs that started seconds apart for
two different events. Latest per name picks exactly one of them. GitHub does
not: it ORs every row bearing a required name, so one red row blocks the merge
while the local reduction reports green.

Measured on head `09506b4cc`:

| job | trigger | step 9 |
|---|---|---|
| 91970285221 | `pull_request` | success |
| 91969707666 | `push` | failure |

Latest per name reported green. `mergeStateStatus` reported `BLOCKED`. The
server was right.

The rule that survives every case measured so far is that the aggregate is not
reconstructable from the rows, because the required-context set is not visible
in them. Ask the server for the aggregate it already computed:

```bash
gh api graphql -f query='query($o:String!,$r:String!,$n:Int!){
  repository(owner:$o,name:$r){pullRequest(number:$n){
    headRefOid mergeable mergeStateStatus
    commits(last:1){nodes{commit{statusCheckRollup{state}}}}}}}' \
  -F o=rjmurillo -F r=ai-agents -F n="$PR" \
  --jq '.data.repository.pullRequest
        | "head=\(.headRefOid[0:9]) rollup=\(.commits.nodes[0].commit.statusCheckRollup.state) state=\(.mergeStateStatus)"'
```

`rollup` is the aggregate over every row on the head commit. `mergeStateStatus`
folds in review threads and branch protection on top of it. Read them together:

| rollup | mergeStateStatus | meaning |
|---|---|---|
| `SUCCESS` | `CLEAN` | mergeable now |
| `SUCCESS` | `BLOCKED` | checks are green, the block is threads or a missing required context |
| `FAILURE` | `BLOCKED` | a real red row, list the rows to find it |
| `PENDING` | `BLOCKED` | still running, not a failure |

Only after `rollup` says `FAILURE` is it worth listing rows, and then the
question is which row, not whether:

```bash
gh pr view "$PR" --json statusCheckRollup --jq '
  .statusCheckRollup[]
  | select((.conclusion // .state) == "FAILURE" or (.conclusion // .state) == "failure")
  | "\(.name // .context)  \(.detailsUrl // "")"'
```

A row whose `conclusion` is null is still running. It is neither a pass nor a
failure, and filtering on "not success" misfiles it as red.
