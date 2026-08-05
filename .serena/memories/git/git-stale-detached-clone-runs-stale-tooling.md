# A Stale Detached Clone Runs Stale Tooling, Not Just Stale Code

**Atomicity**: 95%
**Category**: Git Operations
**Source**: 2026-08-04 fleet session, main clone detached at `c02f61ddd`

## Statement

In a repository that ships the scripts that gate it, a checkout left behind on
an old commit does not merely hold old source. Every validator, hook, and
helper you invoke from that checkout is the version from that commit. The
gates run obsolete logic and report it as fact, with no signal that anything
is out of date.

Before trusting the verdict of any script in this repo, check the working tree
is current:

```bash
git rev-list --count HEAD..origin/main
```

## Context

The conventional warning about a detached `HEAD` is about commits: work
committed there is unreachable once you move away. That framing is incomplete
here. This repository's gates are its own Python: `scripts/validation/`,
`build/scripts/`, `.claude/skills/*/scripts/`. A detached checkout therefore
runs a frozen copy of its own quality system.

The failure is silent in both directions. A bug already fixed on `main`
reappears, and a fix already shipped is invisible. Neither `git status` nor
any hook output mentions the gap, because from the checkout's point of view
nothing is wrong.

## Evidence

The main clone sat detached at `c02f61ddd` (2026-08-02) while `main` had moved
to `58d42a69c`:

```text
git rev-list --count c02f61ddd..origin/main   ->  138 commits
git diff --name-only c02f61ddd origin/main | grep -c '\.py$'   ->  219 script files
```

The concrete cost: `new_pr.py` failed its session-end gate on a file the
branch never touched. The checkout's copy diffed against the **local** `main`
ref, which was six commits behind, so the gate saw 119 changed files instead
of 2 and validated a session log belonging to somebody else's merged PR.

That defect was already filed twice (#4395, #4409) and already fixed by #4461,
and the fix was present on `origin/main` the entire time. Only searching
before filing stopped a third duplicate from being opened against a bug that
did not exist any more.

## Recovery

Verify before moving, because `git checkout` from a detached head is where
work gets orphaned:

```bash
git status --porcelain | wc -l                                # 0 = nothing to lose
git merge-base --is-ancestor HEAD origin/main && echo SAFE    # commit is on main
git checkout main
```

Untracked files survive the switch. Tracked modifications do not, so stash or
commit them to a branch first. If `--is-ancestor` fails, the commit is not on
`main` and switching away orphans it: branch it before you move.

## Related

- `git-stale-branch-fails-repo-state-tests.md` covers the adjacent case: a
  branch that is behind `main` fails tests that read committed repo state.
  That one is about the **diff base**; this one is about the **tooling being
  executed**. A branch can be current and still be run by a stale checkout.
