# Retrospective: Lint Gate Blind Spots (Issues #3792, #3874, #3941, #4060)

## Session Summary

Fixed four lint-gate blind spots in one PR. Branch: fix/lint-gate-blindspots.

## What Went Well

- Re-measurement overturned the #3874 premise: issue claimed zero instances of
  unreachable code, but one real case existed (4 test methods nested inside a
  helper function). Fixing the real bug first, then adding the gate, was correct order.
- RUF100 auto-fix removed 273 dead noqa directives in one batch; the ratchet
  confirmed zero regression.
- Mutation harness: 8/8 mutants killed. The test suite was load-bearing.

## What Went Hard

- Push took 6 attempts. Each surfaced a different ratchet or hook failure.
- The build-all-check (staleness in 39 generated src/copilot-cli files) was
  discovered only on push; running `build/scripts/build_all.py --check` locally
  before push would have caught it.
- RUF100 in per-file-ignore sections for src/copilot-cli/** required explicit
  addition because those paths suppress entire rule families (E, F, W, ...) and
  RUF100 was flagging noqa comments as "non-enabled" even though E402 was
  genuinely active elsewhere.
- retrospective-policy gate fires on every push; a session log or retrospective
  file must exist before pushing.

## Learnings

1. Run `build/scripts/build_all.py --check` locally before push when any
   .claude/skills/** file changes. The generated mirrors in src/copilot-cli/
   will be stale.
2. Create the retrospective file before the first push, not after.
3. The type-ignore-count-ratchet uses --base-ref origin/main and will catch
   type: ignore additions that originated in other PRs that landed on main
   without updating the baseline.
4. `SKIP_SCOPE_CHECK=1` is needed for commits touching > 50 files (bulk
   auto-fix). Document this in the commit message.

## References

- Issue #3792: 464 noqa directives, 331 baseline before RUF100, 58 after
- Issue #3874: 1 real unreachable-code instance found (not zero as claimed)
- Issue #3941: 2 dead noqa tags in eval-model-sweep.py (lines 40 and 365)
- Issue #4060: zero live shadowing instances; added as regression guard
