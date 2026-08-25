# Retrospective: Issue #5123 (push-lock commit guard + head-guard fail-loud)

## Session Info
- **Date**: 2026-08-25
- **Agent**: Claude Code (autoplan-routed session)
- **Task Type**: Bug fix (reliability), two of the issue's three asks
- **Outcome**: Success, with a caught-before-merge correction

## What shipped

Issue #5123 reported that a commit landing in a worktree while that worktree's
own pre-push suite is still running can corrupt any test whose fixture reads
live git state, because the concurrent-commit detector only warned
(`#3109`) instead of failing loud, and nothing prevented the collision in the
first place.

Three commits on `claude/autoplan-goal-joliu2`:

- `73fa615` `fix(tests): fail loud, not just warn, when a concurrent commit
  corrupts a git-state test`. `conftest.py`'s `_guard_real_repo_head` fixture
  now stashes whether a test's call phase failed (new
  `pytest_runtest_makereport` hook) and escalates the existing `#3109`
  warning to a distinct `#5123` `pytest.fail` only when the test that saw the
  HEAD move also failed. A passing test still just warns.
- `d07f8b6` `feat(hooks): refuse a commit while this branch's own push is in
  flight`. New `scripts/validation/check_push_lock_before_commit.py`, wired
  as the `push-lock-commit-guard` pre-commit job, reusing the existing
  canonical push-lock file with a non-blocking probe rather than a new
  scheme.
- `9c10d29` `fix(hooks): add escape hatch and fail open in the push-lock
  commit guard`. Fixes from a security-agent review of the second commit
  (below).

Issue ask #3 (isolating git-HEAD-reading test fixtures behind a throwaway
repo) was scoped out as a broader test-suite refactor, not a bounded fix, and
left as an explicit follow-up recommendation rather than implemented here.

## Failure mode classification

`.agents/governance/FAILURE-MODES.md` #9, **Confident-Incorrectness
Recurrence**: partial signal, premature conclusion, confident delivery.

The first version of the commit guard (`d07f8b6`) shipped two defects of
exactly that shape, both caught by the repo's own `infrastructure-advisory`
pre-commit hook routing `lefthook.yml` changes to a security-agent review
before I pushed, not by me before writing the code:

1. **False scope claim.** The docstring, the block message, `push-lock.md`,
   and the `lefthook.yml` comment all said the guard's protection was
   "in this worktree." It is not: the canonical lock path
   (`.claude/rules/push-lock.md` MUST 1) carries no worktree component by
   design, so the real scope is per branch name per machine. I wrote the
   worktree framing because that is how the *problem* in issue #5123 was
   described, and carried it into the *fix's* scope without checking the
   lock path's own definition against the claim. This is exactly the
   "behavioral claims: read the body, not the name" trap in
   `.claude/rules/canonical-source-mirror.md`: I described what the lock
   does from the issue's framing instead of from `push-lock.md`'s own MUST 1.
2. **No escape hatch, fails closed.** The guard had no bypass and exited 2
   (blocking) on any git error, so an orphaned process holding the lock
   (a killed pre-push job leaving a background child running, which
   `lefthook.yml`'s `timeout:` kills make possible) would have blocked every
   commit on that branch indefinitely, with no documented recovery.

Both were fixed in `9c10d29` before push: `SKIP_PUSH_LOCK_COMMIT_GUARD=1`
escape hatch, fail-open on git error with stderr surfaced, corrected wording
in all five locations, and a live demonstration (holding the real canonical
lock for this branch and confirming the guard both blocks the commit and
reports the accurate "on this machine" scope).

## Evidence

- Security review verdict: APPROVE-WITH-FIXES, seven findings (F1-F7), full
  detail in the review transcript. No exploitable vulnerability (command
  injection, path traversal, symlink/arbitrary-write risk all checked and
  clean, with concrete repro attempts); the real defects were availability
  (F1) and the false claim (F2).
- Live repro after the fix: holding
  `$HOME/src/scratch/locks/push-lock-claude-autoplan-goal-joliu2.lock`
  exclusively made `check_push_lock_before_commit.py` exit 1 with the
  corrected "on this machine" message; releasing it returned exit 0.
- Test coverage: `tests/validation/test_check_push_lock_before_commit.py` (17
  cases: positive/negative/edge for the lock probe, the branch-scoped path,
  the fail-open paths, and the bypass env var) and
  `tests/test_pytest_head_guard.py` additions for the `call_failed`
  escalation (9 new cases: escalate-and-fail, stay-a-warning,
  attributed-mutation-ignores-call_failed, hook wiring both directions).

## Remediation / follow-ups

- This PR itself is the instruction change for the mechanism it adds: it
  extends the canonical `.claude/rules/push-lock.md` with the new "Commit
  guard" section (and its generated `.github/instructions/` mirror). No
  separate governance change is proposed beyond that: the existing
  `infrastructure-advisory` routing to security review already caught the
  defects in the first draft, so the gap was in my own pre-review diligence,
  not in the repo's process.
- Recorded as a follow-up in the PR body rather than a new issue: consider
  isolating git-HEAD-reading test fixtures (`tests/skills/memory/
  test_repair_episode_causal_links.py` and similar) behind a throwaway repo
  fixture instead of reading the real repository's live state (issue #5123
  ask #3). Out of scope for this PR; flagged, not implemented.

## +/Delta

**+ Keep**: routing infrastructure/hook changes through a security review
before push caught a real defect (F1, availability) that unit tests over a
monkeypatched lock directory could not have found, since none of those tests
exercised "no escape hatch exists."

**Delta**: when a fix's framing is inherited from the bug report's own
language (here, "this worktree"), check that framing against the mechanism's
actual defined scope before writing it into the fix, rather than after a
reviewer catches it.
