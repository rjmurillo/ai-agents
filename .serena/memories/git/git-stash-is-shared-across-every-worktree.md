# git stash is repository-global, so `stash pop` can take another agent's work

## The trap

`git stash` stores onto a single stack in the common git directory. Linked
worktrees do not get their own. Every worktree of this repository pushes to and
pops from the same stack, so a concurrent agent can land a stash between your
push and your pop, and your `git stash pop` takes theirs.

This repository routinely runs with 100+ registered worktrees under
`.claude/worktrees/`, so the window is not theoretical.

## What it looks like when it bites

Observed 2026-08-03. Sequence was: edit a rule, `git stash`, switch to `main` to
measure, switch back, `git stash pop`. The pop restored a different agent's
work-in-progress:

```
$ git stash list
stash@{0}: On worktree-wf_82444187-2a1-1: prefixing leftover
stash@{1}: On worktree-wf_82444187-2a1-4: pre-existing worktree changes before pr4095 work
```

The working tree came back carrying 20 modified files from an unrelated
instruction-budget refactor, plus deletions of two files this branch had just
created:

```
 D .serena/memories/decision-agent-self-assessment-does-not-survive-review.md
 D .serena/memories/decision-every-merge-invalidates-every-open-pr.md
 M scripts/validation/instruction_budget.py
 ...
```

The tell is the `On <branch>:` prefix in `git stash list`. A stash created from
a linked worktree carries that worktree's name, so an entry naming a branch you
are not on is somebody else's.

## Do this instead

Do not use `git stash` to park work while you switch refs in a shared checkout.
Commit to your own branch instead; a commit is worktree-local in effect because
it is reachable only from your ref.

To measure another ref without moving your tree, read it directly rather than
checking it out:

```bash
git show main:path/to/file > ~/src/scratch/file.main
```

The same applies to the most tempting case, checking whether a lint or test
failure predates your change. `git stash` to get a clean tree, run the tool, pop
back is the obvious move and it is the one that loses work. Extract the base
version and run the tool on that instead:

```bash
git show origin/main:path/to/file > ~/src/scratch/file.base
uv run --frozen python <the linter> ~/src/scratch/file.base
```

Observed 2026-08-04: the author of this memory reached for `git stash` to check
a taste-lints baseline within an hour of writing it. Three other agents' stashes
were on the stack at the time. The pop happened to return the right entry, which
is luck, not safety.

Most gates in this repository accept a ref argument for exactly this reason, for
example `scripts/ci/taste_count_ratchet.py --base-ref FETCH_HEAD`.

## If it already happened

Do not discard the foreign changes; they are someone's uncommitted work. Park
them back on the stack with a label that says what they are, then restore your
own files from your commit:

```bash
git stash push -u -m "RECOVERED: foreign worktree changes popped from shared stack" -- <their paths>
git checkout HEAD -- <your paths>
```

Verify your own commits were not contaminated before continuing, with
`git show --stat <sha>` on each, since a `git add` of specific paths is
unaffected by the pop but a `git add -A` would not be.

## Related

`.serena/memories/git/git-shallow-is-shared-across-every-worktree.md` is the
same family: `shallow` also lives in the common directory, so one depth-limited
fetch in any worktree blocks the push in all of them.

`git commit` in a compound command is the sibling trap: `git switch X && git
commit` looks safe, but a `switch` that aborts (an untracked file would be
overwritten) still leaves the `commit` to run against whatever branch you were
already on. Observed in the same session, landing a commit on a branch tracking
another agent's PR. Check `git branch --show-current` after any switch that
prints `Aborting`.
