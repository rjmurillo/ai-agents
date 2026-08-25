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

Those three commits were the initial submission to PR #5287. Three automated
review passes (this repo's Copilot code review, Cursor Bugbot, and Devin)
then found further defects across several rounds; each was fixed in its own
commit rather than folded back into the original three. The branch kept
growing commit by commit as each round landed, so an exact total recorded
here would be stale before this file merges; run `git log --oneline
origin/main..claude/autoplan-goal-joliu2` on the branch for the current
count. This is a selected list of the follow-up commits, grouped by what
each one addressed, not an exhaustive or final enumeration:

- `b035853ac` initial retrospective (superseded by this file's own later
  corrections, below).
- `e4545a9f3`, `9f327c269`, `277b3fe41`, `271f9d625`, `f43db7322` (the last
  two resolved by merge commit `972824a6c`): subprocess-encoding and
  git-environment-isolation fixes to the tests this PR added, none of which
  changed the shipped guard's own logic.
- `35a773096`: the dead-code fixture-injection bug described below
  (`request: pytest.FixtureRequest | None = None`).
- `342992121`: corrected a false `SKIP_CLI_E2E` precedent claim, registered
  the new `SKIP_PUSH_LOCK_COMMIT_GUARD` flag in the config catalog, and
  documented the commit guard's residual race window.
- `452b41ca9`: added the missing lefthook wiring test for the new
  `push-lock-commit-guard` job.
- `7dcb5811e`, `d9329971a`: corrected this retrospective's own remediation
  claim, then recorded the `35a773096` defect as a third instance of the
  pattern this file already classifies.
- `0f42efa97`, `2bcb83d27`: regenerated a stale generated mirror and raised a
  vendor-portability baseline, both caught by this repo's own pre-push gates
  rather than by a reviewer.
- `e7cc5dd62`: added Windows-marked tests for the guard's `msvcrt.locking`
  branch, which had no executable coverage anywhere in CI.
- `3a0362c77`: corrected two more citations this file and the config catalog
  had already gotten stale (a symptom in its own right; see Failure mode
  classification, below).
- `81b92aaea`: softened an overclaimed causal statement in the `#5123`
  escalation message from asserting the concurrent commit invalidated a
  failure to stating what the fixture can actually establish.
- `f714ef8ee`: documented `argparse`'s exit 2 in the commit guard's ADR-035
  exit-code contract, with a test.

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

A third, more severe instance of the same pattern shipped past the security
review entirely and was caught only by a later Copilot code review on the
open PR: `conftest.py`'s `_guard_real_repo_head` fixture declared
`request: pytest.FixtureRequest | None = None`. pytest's fixture-argument
scanner excludes any parameter carrying a default from what it resolves as a
fixture dependency, so `request` stayed `None` on every real test run and the
whole `#5123` escalation this PR exists to add was dead code. Confirmed with
a standalone probe (an autouse fixture asserting `request is not None` fails
under real pytest execution with exactly that signature) and with a
discriminating negative control on the new end-to-end integration test:
reintroducing the default makes that test fail with
`AttributeError: 'NoneType' object has no attribute 'node'`, the precise
symptom of the bug. Fixed by removing the default (commit `35a773096`).

This one is worse than the first two because of where it hid. The security
review reads a diff; a defaulted parameter reads as more permissive code, not
as a correctness defect, so nothing in that review's scope would have caught
it. Every test in `tests/test_pytest_head_guard.py` that predated this PR
drives the fixture generator directly via `.__wrapped__()`, which calls the
underlying function outside pytest's dependency-injection machinery entirely,
so none of those 46 passing tests could have observed that the real injection
was broken. The bug was invisible to code review by construction and
invisible to the existing test suite by construction. Only a test that
routes through pytest's actual fixture resolution, which none of them did
until this PR added one, could have caught it.

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
- Test coverage: `tests/validation/test_check_push_lock_before_commit.py`
  (positive/negative/edge cases for the lock probe on both the POSIX
  `fcntl.flock` and Windows `msvcrt.locking` branches, the branch-scoped
  path, the fail-open paths, the bypass env var, and the CLI exit-code
  contract) and `tests/test_pytest_head_guard.py` additions for the
  `call_failed` escalation (escalate-and-fail, stay-a-warning,
  attributed-mutation-ignores-call_failed, hook wiring both directions, and
  a real-pytest-subprocess end-to-end probe). Exact case counts are not
  recorded here: this branch went through several review-driven rounds of
  new tests after this section was first written, so a specific number goes
  stale on the next round. Run `uv run --frozen python -m pytest
  tests/validation/test_check_push_lock_before_commit.py
  tests/test_pytest_head_guard.py --collect-only -q` for the current count.

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
