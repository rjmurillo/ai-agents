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

Measured twice on 2026-08-05, the second time after this section was written.
Both runs: an async push was still going, `git ls-remote` on its ref returned
empty, that emptiness was read as failure, and a second push of the same ref
was launched from the same worktree. Both times the first push then completed
normally and the second one died.

On `docs/stale-checkout-tooling` the second push died on `yaml: unmarshal
errors: mapping key "timeout" already defined`. That error is not real.
`lefthook.yml` is byte identical across worktrees
(`md5 ddf7726679a84c0c09d3de3c39504b99`) and parses clean under a loader that
rejects duplicate mapping keys, no production script writes it, it is absent
from `GENERATOR-FILES.md`, and the tests that write one are scoped to
`tmp_path`. The failure appears only when a second lefthook run overlaps a
first; the writer class behind the torn read is identified under "A push in
flight owns the working tree" below.
The first push landed `* [new branch] 191a73dd13e...` with `PUSH_EXIT=0`.
Roughly eight tool calls went into a config bug that did not exist.

On `docs/gate-measurement-quirks` the second push ran `python-tests (1190.34
seconds)` and then died on `cannot lock ref 'refs/heads/...': reference already
exists`, because the first push had already landed it with `EXIT=0`.

That second message is the one to memorize. It reads like a corrupted ref or a
competing writer. It is neither. It means **your earlier push of this ref
succeeded** and the failing command is the redundant one. Do not delete the
remote branch, force push, or investigate the ref store.

Success is also easy to misattribute. The second push differed by using an
explicit `HEAD:refs/heads/<br>` refspec, inviting the conclusion that the
refspec fixed it. It did not; the refspec push is the one that failed. When two
attempts differ and the ref is present afterward, the attempt that landed it is
the one whose log holds `* [new branch]`, not the last one run.

Never start a second push of a ref while the first is unresolved.

### The ordering that prevents both

Two rules about verifying a push each look right and appear to contradict: "the
check is the shell's exit status" and "verify a push landed by querying the
remote". Both are correct, and both omit the precondition. `git ls-remote`
answers **what landed**, never **whether the work finished**. Before the push
shell resolves, absence is the expected reading for a healthy push and a dead
one alike, so the probe carries no information. After it resolves the same
probe is authoritative.

```bash
read_bash <shellId>                    # 1. wait for PUSH_EXIT
git ls-remote origin refs/heads/"$BR"  # 2. only now does this mean anything
```

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
