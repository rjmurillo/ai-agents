# Skill: Deciding whether a red check belongs to your branch (95%)

## Statement

A failing check on your PR is not evidence that the fault is in your PR. CI runs
your branch merged with `main`, so a defect on `main` fails on every open PR at
once. Attribute the failure only after checking whether `main` is red the same
way.

Check `main` first. It costs one command and it is the discriminator.

```bash
gh run list --branch main --workflow "<Workflow Name>" --limit 5 \
  --json conclusion,headSha,createdAt \
  -q '.[] | "\(.conclusion)\t\(.headSha[0:10])\t\(.createdAt)"'
```

If `main` is failing the same workflow, your branch is a bystander. Merge
`origin/main` once the fix lands and re-run. Change nothing.

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
