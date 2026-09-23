# Retrospective: #3305 retrospective-gate cross-midnight regression guard

**Date**: 2026-07-22 (UTC)
**Issue**: #3305
**Branch**: fix/3305-retrospective-midnight-regression-tests

## What I set out to do

Fix the single-UTC-day false positive I filed as #3305: a session that
does real work on day N and pushes just after 00:00 UTC on day N+1 was
reported to be blocked by the re-homed `retrospective-policy` gate.

## What actually happened (diagnosis reversal)

The filed root cause was wrong. On current main, `check_retrospective_evidence`
is already yesterday-aware. `_recent_date_prefixes` returns today and
yesterday, and both `_today_retrospective_exists` and `_today_session_log`
glob both dates. A frozen-clock reproduction of the exact issue scenario
(yesterday-dated retro file, push at 00:30 UTC) returns rc=0 (pass). A
negative control (two-days-old evidence) correctly blocks. The grace shipped
with the #3295 re-home of the gate into `git_hook_policy.py`, but no
regression test guarded it.

## What I shipped instead

Not a behavior fix (the behavior is correct), but the missing regression
guard. Three tests in `tests/test_lefthook_integration.py`: two positive
(yesterday retro file, yesterday session-log evidence) and one negative
(two-days-old evidence still blocks). Mutation-verified: reverting
`_recent_date_prefixes` to a today-only window flips both positive tests to
BLOCK, proving they catch the regression.

## Failure mode

Primary: FM #9 Confident-Incorrectness Recurrence (`.agents/governance/FAILURE-MODES.md`). The shape matched exactly: partial
signal (a push-time gate rejection), premature conclusion (a today-only
window), confident delivery (I filed #3305 with that mechanism before
reproducing it in isolation). The honest follow-up (reproduce, negate,
mutate) disproved it. Lesson: a push-time gate rejection is a symptom, not a
root cause. Reproduce on a clean tree before filing the mechanism.

## Learnings

1. The retrospective gate's cross-midnight tolerance is exactly one day
   (today + yesterday), enforced on both the retro-file path and the
   session-log path.
2. When a filed bug does not reproduce, the correct deliverable is a
   regression guard plus an accurate issue correction, not a fix for a
   non-bug (which would be manufactured work).
3. Harness note: Copilot CLI 1.0.74-0 denies the `Edit` tool at the harness
   level (exit 2), same class as #3247. Fell back to bash file writes.
