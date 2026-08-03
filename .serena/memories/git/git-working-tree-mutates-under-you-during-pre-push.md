# Skill: Your working tree can mutate under you during a pre-push run (85%)

## Statement

While a pre-push hook is running the full test suite in a worktree, a tracked
source file you never touched can appear as modified, then revert to clean a
few minutes later.

Observed on 2026-08-02 in a linked worktree during a live push:

```diff
-        print("ERROR: ADR changes require a debate log in .agents/critique", file=sys.stderr)
+        print("ERROR: ADR changes require a debate log in .agents/wrong-dir",  # M2 mutant
+               file=sys.stderr)
```

The file was `scripts/validation/git_hook_policy.py`. I made no edit to it. Two
`git diff --stat` readings seconds apart disagreed on the line count, so it was
being rewritten in place. Minutes later the file matched `HEAD` byte for byte
and `grep -c mutant` returned 0. No `M2 mutant` or `wrong-dir` string exists
anywhere under `tests/` or `scripts/` in the committed tree.

The writer was not identified. The shape is a mutation check that edits a guard,
asserts the guard fails, and restores the original. Treat the owner as unknown
and the behavior as real, because the behavior is what costs you.

## Why it is dangerous

The window is exactly the window in which you are most likely to commit. A push
takes about twenty minutes here, so the habit is to keep working, and a
`git add -A` or `git commit -a` during that window silently captures a
deliberately sabotaged validator. That change looks authored, passes review by
eye, and disables a guard on `main`.

## Recipe

Stage by explicit path. Never `git add -A`, never `git commit -a`, in a
worktree with a hook run in flight.

```bash
git add path/to/the/one/file.md
git diff --cached --stat      # confirm only your files appear
git status --porcelain        # anything unexpected here is not yours
```

If an unexpected modification shows up, do not revert it and do not commit it.
Re-read it a minute later. A transient mutant reverts itself, and reverting it
mid-check would make a running assertion fail for the wrong reason.

## Corollary

A guard that fails once, alone, with no code change to explain it is consistent
with a transient mutant being live when that guard ran. This repo saw a single
unexplained `adr_review_policy` failure earlier in the same session. That is a
hypothesis the observation fits, not a proven cause, but it is enough reason to
re-run a lone guard failure before investigating it as a real defect.

## Generalization

A working tree is shared mutable state whenever any automation runs against it.
Treat `git status` as a reading taken at an instant, not as a fact about the
session, and take it again immediately before the commit that depends on it.
