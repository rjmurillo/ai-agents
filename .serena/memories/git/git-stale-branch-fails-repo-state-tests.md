# A Stale Branch Fails Repo-State Tests That Your Diff Never Touched

**Atomicity**: 95%
**Category**: Git Operations
**Source**: 2026-08-01 fleet session, branch `docs/count-ratchet-rule` (PR #4239)

## Statement

Some tests assert the state of committed files rather than the behavior of
code. Those tests fail on any branch that is behind `main`, no matter what the
branch changed. Merge `origin/main` into the branch before pushing.

## Context

Fires at push time. `lefthook.yml` runs the full pytest suite in the pre-push
hook, which takes about 11 minutes, so the failure surfaces only after the wait.

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

## Related

- Never pipe `git push` into `tail`: `$?` then reports `tail`'s status, so a
  rejected push reads as success, and the reject line is truncated away. Use
  `git push origin <branch> > /tmp/push.log 2>&1; echo "EXIT=$?"` and read the
  file.
- `.serena/memories/git/git-merge-preflight.md` for detecting upstream deletions.
