# A Stale Branch Fails Repo-State Tests That Your Diff Never Touched

**Atomicity**: 95%
**Category**: Git Operations
**Source**: 2026-08-01 fleet session, branch `docs/count-ratchet-rule` (PR #4239)

## Statement

Some tests assert the state of committed files rather than the behavior of
code. Those tests fail on any branch that is behind `main`, no matter what the
branch changed. Merge `origin/main` into the branch before pushing.

## Context

Fires at push time. The `python-tests` pre-push job in `lefthook.yml` shells out
to `git_hook_policy.py pytest`, whose `_pytest_commands` runs two pytest
invocations, both deselecting the `integration` marker: the main tree under
`tests/` with `tests/test_safe_push_pr_branch.py` ignored, then that file alone
with `safe_push_transport` also deselected. So the pre-push run is the
non-integration suite, not the whole suite. It still takes about 11 minutes, so
the failure surfaces only after the wait. Re-derive the exact argv with
`git grep -n "not integration" -- scripts/validation/git_hook_policy.py`.

## Evidence

A three-file documentation branch (`.claude/rules/ci-scripts.md` plus its two
generated mirrors) failed its push on exactly one test out of 21181:

```
FAILED tests/skills/memory/test_extract_session_episode.py::
  TestValidateModeRejectsUnusableEventIds::test_the_committed_episode_store_is_clean
= 1 failed, 21180 passed, 31 skipped, 50 deselected in 655.14s =
```

That test reads `.agents/memory/episodes` out of the checkout and pins a
repair (issue #3765). The repair landed on `main` in PR #4233. The branch had
forked before it, so the branch still carried the unrepaired store.

The decisive check, one command on each tree:

```bash
# on main (ebab8e2c97)
uv run --frozen python -m pytest "tests/skills/memory/test_extract_session_episode.py::\
TestValidateModeRejectsUnusableEventIds::test_the_committed_episode_store_is_clean" -q
# 1 passed

# on the stale branch, before merging main
# 1 failed
```

Passing on `main` and failing on the branch, with a diff that touches no Python
and no `.agents/` path, proves the branch's age is the cause.

## Pattern

```bash
git fetch origin main
git merge origin/main --no-edit

# Re-run only the test that failed, which costs seconds instead of 11 minutes
uv run --frozen python -m pytest "<the::failing::test::id>" -q

git push origin <branch>
```

## Why the diagnosis is easy to get wrong

The same push log also prints, from an advisory check:

```
[FAIL] HEAD (<sha>) changes files; a review marker must be an empty commit
       whose Reviewed-By trailer names its parent.
```

That line is not the blocker. `validate_review_marker` is advisory unless
`REVIEW_MARKER_ENFORCED=1` is set (see `scripts/validation/checks_coverage.py`),
and the suite reports `Failed: 0` right below it. Reading that `[FAIL]` as the
cause sends you to write a marker commit that changes nothing.

Read the lefthook job summary at the very end of the log instead. It names the
job that actually failed:

```
  🥊 python-tests (664.44 seconds)
error: failed to push some refs
```

### The glove is only a verdict inside the summary block

`🥊` also appears in lefthook's banner on every run, passing or failing:

```
│ 🥊 lefthook  v2.1.10   hook:  pre-commit │
```

That one is the logo. It carries no verdict, and grepping the log for `🥊`
returns it alongside any real failures, so a commit whose hooks all passed
still shows two or three hits. The verdict markers live only in the block that
starts with `summary:`, where every job gets a `✔️` or a `🥊`. Count those, or
confirm `grep -c "✖"` is 0. On a clean merge commit the summary showed 13 `✔️`
and no failure markers while the banner still printed the glove twice.

## The second decoy: a hook that passed reads as a push that succeeded

`pre_pr.py` ends its own output with these two lines:

```
RESULT: All validations passed

Ready to create pull request!
```

That is the pre-push hook reporting on itself. It is not `git` and it is not
GitHub. If you `tail` the log while the push is still uploading, those lines are
the last thing in the file, and they read as success. They are not.

The push's own result comes after, and looks like one of:

```
 * [new branch]      <branch> -> <branch>
   <old>..<new>      <branch> -> <branch>
error: failed to push some refs
```

Confirm against the remote rather than against the log:

```bash
git ls-remote origin <branch>
```

An empty result means the ref is not there, whatever the log said. This is the
same class of error as reading the advisory `[FAIL]` above: a line that is true
about one thing gets read as a verdict on another.

## The same trap with a diagnostic that actively blames you: count ratchets

The tests above fail with a neutral message. The count ratchets fail with a
message that names the wrong culprit, which is worse, because it sends you to
edit the one file you must never edit.

A ratchet compares the baseline file **on your branch** against the count
measured on `origin/main`. When `main` **lowers** a baseline, a branch that has
not merged `main` still carries the older, higher number. The ratchet reports:

```
ruff count ratchet: BASELINE RAISED. 315 -> 326 (+11) against origin/main.
  The baseline may only fall; lower the count rather than raising the baseline.
taste count ratchet: BASELINE RAISED. 600 -> 601 (+1) against origin/main.
```

Read plainly, that says you widened the allowance. You did not touch the
baseline file at all. Someone else **narrowed** it on `main` and your branch is
behind. Measured 2026-08-02: a branch whose entire diff was `.serena/memories/*.md`
failed both ratchets this way, having touched no Python, no baseline, and no
linted source.

`check_skill_md_portability.py` has the same shape with different words. It
prints `changed measured input: <path>` for a long list of files your diff never
touched, because it is diffing the whole corpus against a baseline that moved on
`main`.

The always-on instruction budget is the fourth instance, and the one whose
output looks least like a staleness problem, because it reports a percentage
rather than a file list:

```
.md         9     83516     83000     21998   100.6%    FAIL
```

A percentage reads as a verdict on your branch's content. It is a ratio, and
both sides of it live in the tree, so either side can move underneath you. Here
the numerator did not move at all: the corpus measured 83516 bytes on the stale
branch and 83516 bytes after merging `main`. The ceiling moved, from 83000 to
84000, and the same corpus went from 100.6% FAIL to 99.4% PASS with no content
change. Read the raw columns, not the percentage. When the measured size is
identical across the merge, the branch was never the cause.

Measured 2026-08-03 on a branch 9 commits behind whose entire diff was two
`.serena/memories/*.md` files, which are not always-on instructions and cannot
move that total: `pre_pr.py` on `origin/main` reported `All validations passed`,
the same command on the stale branch failed Count Ratchets, Skill Markdown
Portability, and Instruction Budget, and one `git merge origin/main` cleared all
three with no other edit.

Run `pre_pr.py` on current `main` first whenever a gate fails on a branch whose
diff plausibly cannot reach it. Main passing and the branch failing localizes
the cause to the branch's age in one command, before you read any diagnostic.

While a fleet is merging, this expires fast. On 2026-08-03 a branch went from
merged-with-main to 8 commits behind, with the taste baseline moved from 597 to
596, during the 7 minutes one `pre_pr.py` run took. Merge `main` immediately
before the push, then re-check only the gates that failed, which costs about 30
seconds, rather than paying another 25 minute push to find out.

The tell in all four: the named files or numbers have nothing to do with your
diff. Before reading one line of the diagnostic, run:

```bash
git fetch origin main && git merge origin/main --no-edit
```

Then re-verify in about 30 seconds rather than paying another 15 minute push:

```bash
uv run --frozen python scripts/ci/type_ignore_count_ratchet.py --base-ref origin/main
uv run --frozen --extra dev python scripts/ci/ruff_count_ratchet.py --base-ref origin/main
uv run --frozen python scripts/ci/taste_count_ratchet.py --base-ref origin/main
```

On the 2026-08-02 instance the merge cleared both ratchets and the portability
checker in one step, with no other change.

Never hand-edit a baseline number to silence this. A baseline may only fall, and
the number that looks wrong on your branch is the correct number on `main`.

## Related

- Never pipe `git push` into `tail`: `$?` then reports `tail`'s status, so a
  rejected push reads as success, and the reject line is truncated away. Use
  Python's `tempfile.NamedTemporaryFile` under `.agents/scratch/`, redirect
  `git push origin <branch>` into that per-run file, then echo and read the exit
  code.
- `.serena/memories/git/git-merge-preflight.md` for detecting upstream deletions.
