# Skill: Deciding whether a red check belongs to your branch (95%)

## Statement

A failing check on your PR is not evidence that the fault is in your PR. CI runs
your branch merged with `main`, so a defect on `main` fails on every open PR at
once. Attribute the failure only after checking whether `main` is red the same
way.

The same reasoning covers a rejected `git push`. The pre-push hook runs the
repo's full gate set, so a red `main` blocks any branch that has merged it,
locally and before any PR exists.

Check `main` first. It costs one command and it is the discriminator.

```bash
gh run list --branch main --workflow "<Workflow Name>" --limit 5 \
  --json conclusion,headSha,createdAt \
  -q '.[] | "\(.conclusion)\t\(.headSha[0:10])\t\(.createdAt)"'
```

If `main` is failing the same workflow, your branch is a bystander. Merge
`origin/main` once the fix lands and re-run. Change nothing.

## Red `main` blocks `git push`, not just CI

The same defect surfaces locally, where there is no PR and no run to inspect.
The pre-push hook runs `scripts/validation/pre_pr.py` and
`scripts/validation/git_hook_policy.py pytest`, so a branch carrying a red
`main` is rejected until it repairs every inherited failure. Each rejection
costs about seventeen minutes.

Read the rejection before assuming your own change caused it. It names the gate
that failed, which is the same discriminator the `gh run list` recipe gives you
on the CI side.

That `gh run list --branch main` check is still the cheapest first move. When it
comes back inconclusive, because the run was cancelled or the gate is
local-only, measure `origin/main` directly. Fetch first: a worktree's
`origin/main` is only as fresh as its last fetch, and probing a stale tree
answers the wrong question.

```bash
git fetch origin main
PROBE=~/src/scratch/mainprobe-$$
git worktree add --detach "$PROBE" FETCH_HEAD
cd "$PROBE"
uv run --frozen python -m pytest <failing node ids> -q
uv run --frozen python scripts/validation/instruction_budget.py
cd - && git worktree remove "$PROBE"
```

Give the probe an unused path. `git worktree add` refuses a path that is already
registered, and a probe left behind from last time will block the next one.

A clean checkout of `main` that reproduces your failure proves you inherited it.
Fix `main` on its own branch. Do not bury the fix inside an unrelated change,
which is what a blocked push tempts you into.

Measured 2026-08-02: `main` at `a72ee868c` failed the pytest gate and the
always-on instruction budget at the same time.

### Two breakages on `main` deadlock the single fix

Each single fix still trips the other gate. A branch fixing only the pytest
failure was rejected on the budget at `83201/83000`; a branch fixing only the
budget was rejected on the same two pytest assertions. Neither could land alone.

The rejections are informative, so this is recoverable in one round trip: each
one names the gate the other fix left broken. The smallest landable unit is both
fixes in one push. Keep them as separate commits so review stays atomic, but do
not try to split the push.

### A branch that predates the breakage pushes cleanly

A branch cut before the breaking commit never runs the gate against it, so that
defect cannot block its push. This proves nothing else. The branch may still
fail other gates, and its CI fails as soon as `refs/pull/N/merge` is recomputed
against a red `main`. Until that recompute it can even show green, for the
caching reason in "Fixing `main` does not fix your PR until the merge ref moves"
below.

So a clean push is not evidence that `main` is green. Check explicitly:

```bash
git merge-base --is-ancestor <breaking-sha> <your-branch>
case $? in
  0) echo "contains the breaking commit" ;;
  1) echo "predates it, so that gate never ran" ;;
  *) echo "git error, resolve the refs first" ;;
esac
```

Do not collapse this into `&& ... || ...`. `git merge-base` exits 128 on an
unknown ref, and the `||` arm would report that as "predates it".

Measured 2026-08-02: `fix/instruction-budget-dedup` pushed without complaint
because it predated the breaking commit, while a branch cut from current `main`
minutes later was rejected.

### `cancel-in-progress: false` does not mean every run completes

A merge burst can leave a defect with no CI evidence at all, which is why the
local probe above is sometimes the only way to see it.

Within one concurrency group GitHub keeps at most one run in flight and one
queued. A newly queued run supersedes the previously queued one and cancels it.
That happens whatever `cancel-in-progress` says, because the setting only
governs whether the RUNNING run is killed.

Measured 2026-08-02 on the Instruction Budget workflow, whose concurrency sets
`cancel-in-progress: ${{ github.ref != 'refs/heads/main' }}`, which is `false`
for a push to `main`:

| Window | Commits pushed to `main` | Runs cancelled | Runs measured |
| --- | --- | --- | --- |
| 21:45:35 to 21:46:20 | 21 | 20 | 1 |

Every cancelled run reported `jobs=0` and lived 2 to 5 seconds, so none of them
started a job. Confirm that rather than inferring it:

```bash
gh run view <run-id> --json conclusion,startedAt,updatedAt,jobs \
  -q '"\(.conclusion) jobs=\(.jobs|length)"'
```

For a whole-tree check this is survivable on its own. The surviving run measures
the tree as it now stands, and nobody needs the intermediate states. It stops
being survivable when the surviving run also skips, which is what a path filter
does when the final commit happens to touch none of the filtered paths. In the
window above the one surviving run skipped `Validate budget`, so 21 consecutive
commits produced zero budget measurements and one green tick.

Treat cancellation and filtering as one failure together, not two separately
tolerable ones.

## Corollary: two differently named red checks can be one bug

Check names are job names, not causes. Two jobs that run the same underlying
script fail together and look like two independent problems.

Measured 2026-08-02: every open PR in the repo showed both `Validate PR` and
`Run Python Tests` red. They were one bug. The taste count ratchet had drifted
to 602 against a baseline of 601, and two separate jobs consume that number:

| Check name | Failing step | What it runs |
|---|---|---|
| `Validate PR` | `Run taste-lint error-count ratchet` | `scripts/ci/taste_count_ratchet.py --base-ref FETCH_HEAD` |
| `Run Python Tests` | `Run pytest` | `tests/ci/test_count_ratchet_against_real_git.py::test_the_shipped_baseline_matches_the_tracked_tree` |

One suppression restored the count to 601 and both went green together.

`Validate PR` in particular does not validate the PR description, despite the
name. Reading the name and inferring the purpose is how the wrong conclusion
gets reached.

## Recipe: get the failing step and node ids, never the check name alone

```bash
BR=$(gh pr view <PR> --json headRefName -q .headRefName)
RID=$(gh run list --branch "$BR" --limit 40 --json databaseId,workflowName \
      -q '[.[]|select(.workflowName=="<Workflow Name>")][0].databaseId')

gh run view "$RID" --log-failed > ~/src/scratch/<pr>-failed.log

# which STEP failed, not which check
awk -F'\t' '{print $2}' ~/src/scratch/<pr>-failed.log | sort -u

# for pytest, the actual node ids
grep -oE "(FAILED|ERROR) tests/[^ ]+" ~/src/scratch/<pr>-failed.log | sort -u
```

`gh run list --workflow` takes the workflow NAME, and the check context shown on
the PR is the JOB name. They frequently differ, so look the run up by
`workflowName` rather than by the failing context string.

The log is large. The run above was 3.8 MB, so redirect it to a file and filter,
rather than reading it inline.

## Evidence

2026-08-02. Six mergeable PRs (#4284, #4102, #4271, #4273, #4274, #4280) all
showed `Validate PR` failing. The same check PASSED on #4290, the branch
carrying the ratchet fix. That contrast proved the gate was working and the
tree was red, rather than the six PRs each being at fault.

`main` runs confirmed it independently: `Python Tests` was `failure` at
`9933b7dbbb` and `77e305c6ed`, and `success` at `15f8756f08` immediately
before. After #4290 merged as `c02f61ddd2`, both checks went green with no
change to any of the six PRs.

## Fixing `main` does not fix your PR until the merge ref moves

CI for a `pull_request` event checks out `refs/pull/N/merge`, a ref GitHub
computes by merging your branch into the base. That ref is cached. When `main`
gains a fix, your PR keeps running against the pre-fix tree until something
forces a recompute, so the same check keeps failing for a cause that no longer
exists on `main`.

Three ways of forcing it were measured on 2026-08-02 after `c02f61ddd2` landed.
All three failed:

| Attempt | Result |
| --- | --- |
| `gh run rerun` / `--failed` | Replays the original event payload. Same tree. |
| `gh pr edit --body-file` (fires `edited`) | New run, merge ref unchanged. |
| `gh api repos/O/R/pulls/N` | Returns the cached `merge_commit_sha` when `mergeable` is already `true`. |

What worked was a push to the branch, which fires `synchronize`. #4284 pushed a
`Merge origin/main` commit 51 seconds after the fix landed and got a fresh ref.
#4271, #4274, and #4102 had not pushed since before the fix and all three were
still stale over fifteen minutes later.

Verify rather than assume, because the check name will not tell you:

```bash
git fetch origin refs/pull/<N>/merge:refs/tmp/m<N> -f
git merge-base --is-ancestor <fix-sha> refs/tmp/m<N> && echo FRESH || echo STALE
```

Do not use `gh run view --json headSha` for this. On a `pull_request` run that
field is the branch tip, not the merge commit, so it is unchanged by a rerun and
unchanged by a base move. It cannot distinguish the two cases.

## Anti-Pattern

Editing a baseline, adding an unrelated suppression to a file you happen to be
touching, or passing a skip flag, in order to clear a check that is red because
`main` is red. It hides the real defect and a baseline may only fall.

Equally wrong in the other direction: assuming a failure is inherited without
checking. The rule is to measure `main`, not to pick a default.

## Related

- `ci-count-ratchet-never-names-the-offending-file.md` (locating the offender once you own the failure)
- `ci-file-size-ratchet-line-numbers-shift.md` (why violation identities move)
