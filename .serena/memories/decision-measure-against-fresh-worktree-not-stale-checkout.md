# Measure against a fresh worktree at `origin/main`, not your checkout

## Question

A traceback, a failing test, or a line number is about to go into an issue, a
PR body, or a comment. Which tree should it be measured against?

## Conventional answer

Your working checkout. You just ran the command and saw the output, so the
output is real.

## First-principles position

The output being real does not make the conclusion true. A long-running
session drifts far behind `origin/main` while other work merges. A real
traceback measured against a tree nobody is running produces a true
observation and a false conclusion, and it can invert cause and fix: the
commit you blame may be the one that fixed it, and the fix you propose may
already be on `main`.

This is not a rare edge. Measured twice in one session: the main checkout was
102 commits behind at one point and 129 at another.

## Evidence

Issue #4188 asserted that PR #4174 broke a test. Three independent checks
against `origin/main` showed the opposite: `git log -S <symbol>` returned one
commit introducing the failure (#4144), `git show <sha>:<file>` confirmed the
pre-fix and post-fix shapes, and the issue was filed 55 minutes after the fix
merged. The attribution was exactly inverted. Acting on its suggested fix
would have been a no-op at best.

Separately, a negative-control exemplar cited from a stale checkout as
`tests/eval/test_providers.py:977` was actually at line 985 on `origin/main`.

## Decision

Before measuring anything destined for a durable artifact:

```
git fetch origin main
git rev-list --count HEAD..origin/main
```

State that number. If it is not zero, measure in a fresh worktree instead:

```
git worktree add /tmp/wt_<name> -b <branch> origin/main
```

A fresh worktree costs about 90 seconds to provision its venv (112 packages).
That is cheaper than a wrong issue, and far cheaper than a fix applied to the
wrong commit.
