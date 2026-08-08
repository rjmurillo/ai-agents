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

## The converse: absence from the remote is not failure

The trap above is a push that finished carrying nothing. The mirror image is a
push that is carrying something and has not finished yet.

Because every pre-push step runs against the full suite, a real push here takes
minutes, not seconds. The 660 second figure above is the reference point. So
for the first ten-plus minutes of any genuine push, the branch is absent from
the remote, and that absence looks exactly like a failure.

Measured 2026-08-05. An async push of a two file memory branch was still
running. `git ls-remote origin refs/heads/docs/stale-checkout-tooling` returned
empty. Reading that as failure, a second push of the same ref was launched from
the same worktree while the first was still in flight. The second one died on:

```text
Error: yaml: unmarshal errors:
  line 424: mapping key "timeout" already defined at line 417
  line 425: mapping key "run" already defined at line 418
  line 426: mapping key "glob" already defined at line 421
error: failed to push some refs
```

That error is not real. `lefthook.yml` is byte identical across worktrees
(`md5 ddf7726679a84c0c09d3de3c39504b99`) and parses clean under a loader that
rejects duplicate mapping keys. So does the shared checkout's different copy.
No production script writes `lefthook.yml`, it is absent from
`GENERATOR-FILES.md`, and the tests that do write one are all scoped to
`tmp_path`. What is established is that the failure only appears when a second
lefthook run overlaps a first, and that the config it complains about is valid.
The writer class behind the torn read was later identified; see the next
section.

The first push then completed normally, `* [new branch] 191a73dd13e... ->
docs/stale-checkout-tooling`, `PUSH_EXIT=0`. Roughly eight tool calls went into
investigating a config bug that did not exist.

The check is the shell's own exit status, not the remote:

```bash
# right: ask the process that is doing the work
read_bash <shellId>          # wait for PUSH_EXIT

# wrong while a push is in flight: absence here proves nothing
git ls-remote origin refs/heads/"$BR"
```

Never start a second push of a ref while the first is unresolved. Overlapping
lefthook runs produce failures that describe the wrong subsystem.

## A push in flight owns the working tree

The pre-push chain runs for roughly eleven minutes against the **live working
tree**, not against the pushed commit. Measured on one run: `pre-pr-validation`
59s, `python-tests` 654s, plus generators and ratchets. Any file edited in that
worktree during the window is read by the running chain.

Two things follow, both observed in the same run:

1. **The push fails.** A file mutated mid-flight for an unrelated experiment
   left `python-tests (654.08 seconds)` then `PUSH_EXIT=1`. Eleven minutes
   spent, nothing pushed, and the failure named a test rather than the edit.
2. **Generated mirrors silently absorb the edit.**
   `build/scripts/generate_skills.py` copies `.claude/skills/**` into
   `src/copilot-cli/skills/**` (97 skills, 620 files written) straight from the
   working tree. A mutation to `.claude/skills/github/scripts/pr/new_pr.py`
   reappeared in `src/copilot-cli/skills/github/scripts/pr/new_pr.py` with no
   command of mine having touched the mirror. Restoring only the source leaves
   the mirror dirty, which then reads as unexplained drift.

Ruled out individually as the writer, each with the mutation live and no push
running: a scoped `pytest` of one file, `tests/build_scripts` (1555 passed),
`scripts/validation/pre_pr.py`, and `build/scripts/build_all.py --check`. None
touched the mirror. The generator does exactly this transformation on demand,
so the class is proven even though the specific job inside the chain is not
named.

Rule: treat a worktree with a push in flight as read only. Mutation experiments
belong in a different worktree, or after `PUSH_EXIT` is known. When a mirror
turns up modified and no command of yours wrote it, check for a push in flight
before hunting a generator bug.

## Generalization

Three different measurements get confused for one another, and the workflow
supplies them in the least useful order.

| Question | Signal that answers it | Signal that does not |
|---|---|---|
| Has the push finished? | the shell's exit status | the remote ref, absent until it lands |
| Did the push succeed? | `PUSH_EXIT=0` | elapsed time |
| What did the push carry? | the hook summary, `rev-list --count` | `PUSH_EXIT=0` |

`REAL_EXIT=0` answers whether the push finished, never what it carried.
Completion and content are different measurements, and the push workflow
supplies only the first. The hook summary is the cheapest content signal
available for free: a run where nothing matched is a run where nothing was
sent.

Symmetrically, the remote answers what landed, never whether the work is still
running. Polling a side channel for a result the primary channel has not
produced yet invents failures, and acting on those invented failures creates
real ones.

## The inverse trap: an empty `ls-remote` usually means "not yet" (95%)

The failure above is a push that finishes too fast. The opposite misread costs
more, and it looks identical to a real failure.

A push here runs the whole lefthook pre-push suite before a single byte moves.
Measured 2026-08-05: `python-tests` alone took 914 seconds, and the full push
took over 14 minutes wall clock with a second agent's push competing for CPU.
For that entire window `git ls-remote origin "$BRANCH"` prints nothing, because
the ref genuinely does not exist yet.

Nothing separates that from a rejected push by looking at `ls-remote` alone. On
2026-08-05 I read the empty output as failure and nearly re-pushed, which would
have started a second 15 minute suite and left two pushes racing the same ref.

Check liveness before concluding anything:

```bash
git ls-remote origin "$BRANCH"                       # empty is ambiguous
pgrep -af 'git push origin' | grep -Fc "$BRANCH"     # 0 means it really ended
```

Only when the process count is 0 does an empty `ls-remote` mean the push
failed. While the count is above 0, empty means "still running".

Two related traps in the same window:

- `tail` on a live push log lands in the middle of hook output, so it reads as
  finished when it is not. One real log reached 24,613 lines. Compare
  `wc -l` across two reads instead; a stalled count plus a live process means
  a long hook is running, not a hang.
- `Ready to create pull request!` appears in that log well before the push
  completes, so it is not a completion signal either.

## Generalization, second form

An absent ref and a pending ref produce byte-identical output. Any check whose
negative result is indistinguishable from "too early" needs a liveness probe
next to it, or it is not a check. Pair the query with the process table, not
with a longer wait.
