# A Whole-Corpus Gate Cannot Be Guarded By A Per-Change Path Filter

**Atomicity**: 94%
**Category**: CI design, first-principles contradiction
**Source**: 2026-08-02 fleet session. Issue #4345, PR #4351, commits a72ee868c
through 160d1670a. Extended 2026-08-03 with the concurrency-supersession
mechanism, issues #4350 and #4176.

**Scope note.** A gate on `main` can fail to measure the tree for three
independent reasons. This file covers all three because they compose, and
fixing one leaves the others live:

1. The run is **cancelled while pending** and never creates a job. See
   "Mechanism three" below. Largest hole: 25 to 43 percent of main pushes.
2. The run executes but the job is **path-filter skipped**, and the skip job
   reports success. The original subject of this file.
3. The breach itself is admitted because **required checks are not strict**,
   so each PR passes honestly against its own base and only the union breaks.

Diagnosing one and stopping is the trap. All three were live simultaneously in
this repo on 2026-08-02.

## The conventional wisdom this contradicts

Standard CI practice says to gate each job on whether the change touched files
that job cares about. `dorny/paths-filter` exists for exactly this, and for
per-file checks it is correct and saves real time.

Applied to a gate whose verdict is a **sum over the whole tree**, the same
pattern is not an optimization. It is a correctness bug, and it fails in the
most expensive direction: the workflow reports **success** without measuring
anything.

## The reasoning

A per-file check answers "is this file valid." Its truth depends only on the
files in the diff, so filtering on the diff preserves the answer.

A whole-corpus check answers "is the total under the ceiling." Its truth depends
on the entire tree, so it can change when the diff is **empty with respect to
the filter**. Filtering on the diff does not preserve the answer, it discards
it.

Worse, the failure is absorbing. Once a breach exists, every later commit that
does not touch the filtered paths re-reports green. Nothing re-measures until
someone happens to edit a filtered file. The breach is silent and unbounded in
duration.

## Evidence

`.github/workflows/instruction-budget.yml` gated `validate-budget` on whether
the change touched `.claude/rules/**` or `.github/instructions/**`. The gate
sums the always-on instruction corpus per language against a byte ceiling.

Measured at `a72ee868c`, which was `main`:

```
Ext     Files     Bytes   Ceiling   Tokens~    Usage  Status
.md         9     83201     83000     21949   100.2%    FAIL
```

The workflow run for that same SHA reported `conclusion success`. Job level,
which is the proof rather than the inference:

```
gh api repos/rjmurillo/ai-agents/actions/runs/30768626850/jobs
  Detect changes            => success
  Skip budget (no changes)  => success
  Validate budget           => skipped
```

The measurement that would have failed was `skipped`, and the job that reported
`success` measured nothing. The squash of #4105 touched no rule files.

Always go to the **jobs**, not the run conclusion. A run whose only executed job
is a skip-announcer is indistinguishable from a run that verified the tree if
you stop at `conclusion`.

The same validator runs in the pre-push hook, so while CI was green, **every
push in the repository failed**, on every branch, regardless of content. Two of
my own branches failed with diffs of `scripts/validation/pre_pr_sequence.py`
and `.serena/memories/*.md` respectively, neither of which is an instruction
file.

## The second half: an absolute ceiling plus non-strict required checks

The breach itself came from a semantic conflict, not a defective PR:

```
commit       PR      total   note
a6c16da8d    #4329   82603   397 bytes headroom
43eb2c14e    #4281   82942   +339 to knowledge-persistence, 58 left
7b5279967    #4113   83201   +259 to universal, over by 201
```

Each PR was measured against its own base and passed honestly. No two of them
touch the same file. The ceiling is a sum, so the breach exists only after both
land. At the time, `strict_required_status_checks_policy: false` on ruleset
11104075 permitted exactly this. With strict reverted to false (2026-08-10), admission is no longer
serialized by the ruleset; the count ratchets still enforce practical freshness
for PRs touching ratcheted counts.

Any absolute (non-diff-relative) ceiling has this property. A ratchet that
compares against `origin/main` does not, which is why the count ratchets caught
their own drift and the budget did not.

## The residual risk this leaves

`PR #4351` restored green by trimming bytes only (`Refs #4345`, not `Fixes`).
Measured at `160d1670a`:

```
.md         9     82992     83000     21895   100.0%    PASS
```

That is **8 bytes** of headroom. Any rule edit adding a single short sentence
re-breaches.

`PR #4361` (`06299410b`) first added `FORCE_RUN_EVENTS: push` to
`instruction-budget.yml`, which closed mechanism two on push to main and left
`pull_request` filtered. Issue #4345 then deleted the filter, the `check-paths`
job and the `skip-budget` job outright, so that env var, that header comment,
and the whole filter are gone from the file. Do not go looking for them: the
workflow now holds one unconditional `validate-budget` job. Neither shape
closes mechanism three below, because a run cancelled while pending never
reaches the job, so forcing or unconditioning the job inside it changes
nothing. Verify such a fix against run **jobs** across a burst of merges, never
against the workflow source.

Running an absolute ceiling at 100.0 percent utilization is still brittle. The
strict flip (when active) weakened the concurrent-admission mechanism because a stale second PR
had to refresh and re-run against the merged result. With strict now off, the
concurrent-admission risk returns. The capacity answer remains a
**reserve band**: fail or warn at PR time when the merged result would leave less
than a threshold of headroom, so one PR cannot consume the last bytes and leave
the next routine edit blocked.

## Mechanism three: a pending run is evicted regardless of cancel-in-progress

This one is larger than the path filter and was invisible for two days because
it leaves **no artifact anywhere**. Found 2026-08-03.

The conventional reading of GitHub's docs is that `cancel-in-progress: false`
means "runs in this group are never cancelled." That reading is wrong.
`cancel-in-progress` governs runs that are **already running**. It says nothing
about the queue, and a concurrency group holds **at most one pending run**. When
a third run arrives while one is running and one is pending, the pending one is
**evicted and marked `cancelled`**, and `cancel-in-progress: false` does not
suppress the eviction.

So during a merge burst, only the last push in the burst survives.

Measured on `instruction-budget.yml`, whose concurrency block at the time
already read `cancel-in-progress: ${{ github.ref != 'refs/heads/main' }}`:

```
2026-08-02T21:46:20Z ev=push concl=success   head=a72ee868c
2026-08-02T21:46:18Z ev=push concl=cancelled head=8fccc019c
2026-08-02T21:46:16Z ev=push concl=cancelled head=7b5279967
... 16 more consecutive cancellations ...
2026-08-02T21:45:35Z ev=push concl=cancelled head=3a1bf9df7
```

19 consecutive cancelled pushes to `main` in 45 seconds, one survivor. Note the
compounding: the single survivor is the one that then **skipped** via mechanism
two. Twenty-one merges, zero measurements.

The eviction happens before any job is created, which is why nothing is left to
find:

```
gh api repos/rjmurillo/ai-agents/actions/runs/30768601554
created=2026-08-02T21:45:41Z updated=2026-08-02T21:45:45Z concl=cancelled

gh api repos/rjmurillo/ai-agents/actions/runs/30768601554/jobs
(zero jobs)
```

Cancelled four seconds after creation with zero jobs. Consequently
`gh api repos/OWNER/REPO/commits/<sha>/check-runs` returns **no entry for that
workflow at all**. Not a failure, not a skip: absent. Both the git side and the
check-runs side look clean.

### Blast radius, measured 2026-08-03

`gh api ".../actions/workflows/<id>/runs?branch=main&event=push&per_page=100"`,
counting `cancelled`:

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

The post-merge safety net on `main` has a 25 to 43 percent hole, by workflow.

### Why the previous fix did not work

Issue #4176 diagnosed this class on 2026-08-01 and closed after changing
`cancel-in-progress: true` to `cancel-in-progress: ${{ github.ref != 'refs/heads/main' }}`
in six workflows. That expression is correct and does evaluate to `false` on
main. The burst above is from 2026-08-02, a day later, with that fix already in
the tree (verified by `git show 7b5279967:.github/workflows/instruction-budget.yml`).
Necessary, not sufficient.

The bug is in the **group key**, not in `cancel-in-progress`. Every push to main
shares the group `<workflow>-refs/heads/main`, so every push is a candidate for
eviction. Give main pushes a group per commit and there is nothing to evict:

```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}-${{ github.ref == 'refs/heads/main' && github.sha || 'shared' }}
  cancel-in-progress: ${{ github.ref != 'refs/heads/main' }}
```

Push to main gets a unique group per commit. Branch pushes and pull requests end
in the constant `shared` and keep today's stale-run cancellation. Preserve each
workflow's existing group prefix; `codeql-analysis.yml` uses a literal
`codeql-analysis-` and `validate-generated-agents.yml` uses `validate-agents-`.

Enumerate the class rather than trusting a list:

```bash
for f in $(git ls-tree -r --name-only origin/main -- .github/workflows | grep -E '\.ya?ml$'); do
  body=$(git show "origin/main:$f"); grep -q '^concurrency:' <<<"$body" || continue
  grp=$(sed -n '/^concurrency:/,/^[a-z]/p' <<<"$body" | grep -m1 'group:'); [ -z "$grp" ] && continue
  if grep -qE 'github\.ref' <<<"$grp" && ! grep -qE 'github\.sha' <<<"$grp"; then
    grep -qE '^\s*push:' <<<"$body" && echo "  $(basename $f)"
  fi
done
```

### The generalization

A concurrency group is a **serialization point**. Putting a post-merge verifier
inside a group shared by every merge means the verifier can only observe the
tree as fast as merges arrive. Under a burst it observes nothing. Anything whose
job is to witness every commit must be keyed per commit; group only the things
you are willing to lose.

## How to recognize this class

Ask of any gate: **does its verdict depend on files outside the diff?** If yes,
it cannot be path-filtered, and it must run on every push and every PR. Candidates
in this repo are the instruction budget, the count ratchets, the portability
baselines, and the memory index counts.

A useful smell: a workflow that has a `Skip <thing> (no changes)` job which
reports success. For a per-file check that is correct. For a whole-corpus check,
a skipped measurement reporting success is precisely the defect.

Then ask the second question: **is this gate the only thing that would witness a
bad commit?** If yes, it must not share a concurrency group with other commits.
Check the group key, not `cancel-in-progress`.

## Auditing whether a gate actually ran

Neither the workflow source nor the run conclusion answers this. Three levels,
each of which can lie about the one above:

| Level | Command | Lies when |
|---|---|---|
| workflow source | `git show main:.github/workflows/X.yml` | the run was cancelled while pending, or the job was skipped |
| run conclusion | `gh api .../actions/runs/<id>` | the only executed job was a skip-announcer |
| **run jobs** | `gh api .../actions/runs/<id>/jobs` | authoritative |

And a run that never existed leaves nothing at any level. To detect that, list
runs by branch and look for gaps and for `cancelled` with zero jobs:

```bash
gh api "repos/OWNER/REPO/actions/workflows/<id>/runs?branch=main&event=push&per_page=100" \
  --jq '.workflow_runs[] | "\(.created_at) \(.conclusion) \(.head_sha[0:9])"'
```

Get `<id>` from `gh api "repos/OWNER/REPO/actions/workflows?per_page=100"`. The
default page size is 30 and this repo has 72 workflows, so an unpaged lookup
silently misses two thirds of them; that cost a wrong "NOID" result once.

Check-runs on a **squash** merge commit are not the PR's checks. The repo is
squash-only, so `gh api repos/.../commits/<merge_sha>/check-runs` shows only what
ran on the push to main. To see what a PR ran, resolve
`gh api repos/.../pulls/N --jq .head.sha` first and query that SHA.

## Diagnosis when it bites you

Symptom: a push fails on a gate that has nothing to do with your diff. Apply the
red-main diagnostic, which now stands at 5 for 5 in this repo:

```bash
git worktree add -q --detach ~/src/GitHub/rjmurillo/ai-agents-probe-<slug> origin/main
cd ~/src/GitHub/rjmurillo/ai-agents-probe-<slug>
uv run --frozen python scripts/validation/instruction_budget.py --ci
```

Reproducing on pristine `origin/main` proves the branch is innocent and moves
the investigation to `main` in one command. Do not start by reading your own
diff.

## Bisecting a byte-budget breach cheaply

Do not check out each commit. Sum blob sizes straight from the object database,
which takes seconds over 40 commits:

```bash
FILES="<space separated paths the gate measures>"
for c in $(git rev-list --first-parent -40 origin/main); do
  tot=0
  for f in $FILES; do
    s=$(git cat-file -s "$c:$f" 2>/dev/null || echo 0); tot=$((tot+s))
  done
  printf "%s %6d %s\n" "$(git rev-parse --short $c)" "$tot" "$(git log -1 --format=%s $c | cut -c1-62)"
done
```

Get the exact file list from `--format json` rather than guessing it. The `.md`
bucket and the `.py` bucket differ by which `applyTo` globs match, so the file
sets are not the same.

## Related

- Issue #4752 applied this rule to `validate-vendor-portability.yml`. Its six
  ratchets inspect the repository tree, so the fix removed the dorny filter,
  change-detector job, and success-producing skip job instead of forcing only
  pushes through the filter.
- `ci/ci-infrastructure-006-required-check-path-filter-bypass.md` is the
  **opposite** failure: a path filter stops a required check from ever
  reporting, so the PR waits forever. That one is loud and self-announcing.
  This one is silent and reports success. Same mechanism, opposite blast radius.
- `git/git-stale-branch-fails-repo-state-tests.md` for the branch-age variant,
  including the count ratchet that says BASELINE RAISED when `main` lowered it.
- Issue #4057 asks that required checks evaluate the actual merge tree, which is
  the second half of this defect.
- Issue #4350 tracks mechanism three (`pytest.yml`, 43 of 100 main pushes
  cancelled). Issue #4176 is its predecessor, closed 2026-08-01 on a fix that
  measurement later showed to be necessary but not sufficient.
- Issue #4345 is the instruction-budget breach itself; `PR #4361` shipped the
  push-to-main force-run.
