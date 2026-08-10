# Proving a guard is load-bearing by adding code runs that code for real

## The trap

Revert-sensitivity testing checks that each half of a change is doing work: you
undo one piece, run the suite, and confirm something goes red. A half that stays
green was decoration.

Most halves are undone by taking something away. Delete the new branch, neuter
the new condition, drop the new argument. Those are safe by construction,
because removing behavior cannot make the process do anything it was not
already able to do.

The dangerous half is the one you undo by putting something **back**. If the
change you are proving removed a destructive command, the revert re-adds it, and
now the suite executes it. Whether that reaches the real world depends on
something the test author never thought about: how far down the call stack the
mocks go.

Tests mock the dependency the subject is known to have. Injecting code gives the
subject a dependency no test knew to declare, so nothing patches it.

## What it looked like when it bit

Observed 2026-08-05 in `ai-agents`, proving the halves of a redesign of
`scripts/maintenance/gc_worktrees.py`. The redesign had deleted a blanket
`git worktree prune`. Revert six put it back, at the top of the candidate loop
in `apply_removals`:

```python
_run_git(["worktree", "prune", "-v"])   # injected by the revert harness
```

The apply tests in `TestApply`, `TestPlanMatchesApply`, and the whole
time-budget suite patch `remove_worktree`. That is the only side-effecting
dependency `apply_removals` had, so patching it reads as full containment. It
is not. `_run_git` was never patched, because nothing in the real code needed
it patched, and `_run_git` shells out with the current working directory, which
was the repository root.

A real `git worktree prune` ran against the live repository. It removed all 62
stale admin entries.

Nothing announced it. The revert harness reported exactly what it was built to
report, that the suite went red, which was true and was the intended result.
The damage was a side effect of getting the right answer. It surfaced later,
from an unrelated dry run:

```
$ git worktree list --porcelain | grep -c '^worktree'
294                          # was 356, and 356 - 294 = 62
$ git worktree list --porcelain | grep -c '^prunable'
0                            # all 62 stale entries gone
```

The count matching the stale set exactly is what identified the cause.

Blast radius here was zero, by luck rather than design. Two independent checks
minutes earlier had confirmed every one of the 62 HEADs was contained by some
ref, and `git worktree prune` deletes admin directories, not refs, so no commit
lost its last anchor. All 50 named branches verified present afterward. The
12 detached entries cannot be re-verified after the fact, because the plan file
recorded `path`, `branch`, `remove`, and `reason`, and no SHA. That gap is the
real lesson about evidence: an artifact you might need for a post-mortem should
carry the identifier, not just the label.

## Do this instead

Sort every revert by its direction before running any of them.

- **Subtractive** (delete a branch, neuter a condition, drop a guard): run it in
  place. It cannot reach further than the code already could.
- **Additive** (put back a call, re-add a command, restore a removed step):
  do not run it in place.

For an additive revert, pick one:

```bash
# 1. Run the experiment in a throwaway clone, not the repository you work in.
git clone --no-hardlinks <repo-path> ~/src/scratch/revert-sandbox
git -C ~/src/scratch/revert-sandbox remote remove origin
```

Or patch the process boundary rather than the helper, so no injected call can
escape whatever the test forgot:

```python
# conftest.py for the experiment only
@pytest.fixture(autouse=True)
def _no_subprocess(monkeypatch):
    monkeypatch.setattr(target_module, "_run_git", lambda *a, **k: "")
```

Or make the injection inert: assert that the call *would* happen instead of
making it happen. A `raise AssertionError("blanket prune reintroduced")` in
place of the command proves the same halves are load-bearing and cannot touch
anything.

The general form: **the mock has to sit at the boundary the injected code
crosses, not at the boundary the original code crossed.** Those are the same
place only when you are removing code.

## Detecting it after the fact

An injected command leaves no trace in the harness output, so check state
rather than logs. Take a cheap census before the experiment and diff it after:

```bash
git worktree list --porcelain | grep -c '^worktree'   # before and after
git rev-list --all --count
git stash list | wc -l
```

A number that moved during a run that was supposed to be read-only is the
signal. This is worth doing for any experiment against a repository you care
about, not only additive ones.

## Related

`testing/mutation-harness-pins-the-comment-you-are-editing.md` is the same
family: a harness that edits real code to prove a point, where the edit itself
is the hazard. `git/git-a-subagent-in-your-worktree-moves-your-head.md` is the
delegation version, an agent running git in a checkout someone else owns, and
its throwaway-clone recipe is the one to reuse here.
