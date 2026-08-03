# Skill: A pre-push run that skips every hook means the push carries no commits (95%)

## Statement

Lefthook reports `(skip) no matching push files` for a step when the pushed
range contains no file matching that step's glob. When *every* step reports it,
including `python-tests`, `pre-pr-validation`, `security-scan` and
`build-all-check`, the range itself is empty. The push is a no-op.

That reads like a validation bypass. It is not one. The hooks are right and the
push is wrong.

Measured 2026-08-02: a push reported `* [new branch] HEAD -> fix/...` and
`REAL_EXIT=0` in ten seconds, on a repository where the previous push of a
comparable branch took roughly 660 seconds. Every lefthook step skipped.
`gh pr create` then refused the branch with `No commits between main and
fix/...`, and `git ls-remote` showed the new branch and `main` at the same sha.

## Cause

The worktree was in detached HEAD at the tip of `main`:

```text
9c1c25c21  commit: fix(tests): stop the CI env var choosing the assertion
22588a0f4  checkout: moving from fix/command-size-test-ci-env-leak to HEAD~1
```

The detach was a deliberate verification step: check out the parent commit,
confirm the test fails without the fix, prove the fix is load bearing. The
checkout back to the branch never happened. Pushing `HEAD` then sent `main`'s
tip under the feature branch name, which is a legal operation that git reports
as success.

Every signal that normally confirms a push agreed with itself. `git rev-parse
HEAD` returned a plausible sha, `git ls-remote` returned the same sha, and the
log ended in `REAL_EXIT=0`. All three were true statements about the wrong
commit.

## Recipe

Check the branch, not the sha. A detached worktree returns an empty string,
while `git rev-parse HEAD` looks perfectly healthy.

```bash
test -n "$(git -C "$WT" branch --show-current)" || echo "DETACHED, do not push"
```

Then confirm the push has content. This one check catches detached HEAD, an
accidentally reset branch, and an already merged branch together.

```bash
git -C "$WT" rev-list --count origin/main..HEAD   # ahead count, must be > 0
git -C "$WT" diff --stat origin/main...HEAD       # must list only your files
```

The diff needs three dots and the count needs two. Three dots diff from the
merge base, which is what the pull request shows. Two dots diff from the current
tip of `main`, so the moment `main` advances they report every change you have
not merged yet as though you were reverting it. Measured 2026-08-02 on a branch
three commits behind: two dots reported 29 files and 1315 deletions, three dots
reported the 5 files actually changed, and `gh pr view --json files` agreed with
the three dot answer.

Recovery does not need a force push. `git checkout $BR` reattaches, and because
the wrongly pushed commit is an ancestor of the real one, a plain
`git push origin $BR` fast forwards. Prove it first:

```bash
git merge-base --is-ancestor "$WRONG_SHA" HEAD && echo fast-forward-safe
```

## Generalization

`REAL_EXIT=0` answers whether the push finished, never what it carried.
Completion and content are different measurements, and the push workflow
supplies only the first. The hook summary is the cheapest content signal
available for free: a run where nothing matched is a run where nothing was
sent.
