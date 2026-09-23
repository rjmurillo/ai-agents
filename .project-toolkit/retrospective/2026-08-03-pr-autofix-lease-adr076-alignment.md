# Retrospective: PR Autofix Lease ADR-076 Alignment (Issues \#4375, \#4376, \#4377)

## Retrospective Section

- **Date**: 2026-08-03
- **Branch**: fix/pr-autofix-lease
- **Issues**: \#4375, \#4376, \#4377
- **Outcome**: All three fixed, 111 tests passing, mutation-proven

## Learnings Captured

### What worked well

- Triaging all three issues against origin/main before writing code confirmed
  \#4375 SHA defect was already partially fixed; the remaining defect (auth
  fail-open) was distinct and still present.
- The `try/except SystemExit` pattern in `main()` is the correct shape for
  ADR-076 part 3 step 6 fail-open. Using `except SystemExit as exc` catches
  both `assert_gh_authenticated()` exit(4) and `resolve_repo_params()` exit(3).
- `renew` as a named alias routing to `acquire()` avoids duplicating lease
  logic. ADR-076 part 3 step 4 already defines self-renewal semantics; the
  `renew` subcommand is purely a caller-facing convenience.
- Mutation testing caught nothing wrong; the cosmetic control survived
  correctly, confirming the harness measured the right thing.

### What cost extra turns

- **Taste baseline drift**: Three separate origin/main advances during the
  push window caused taste_count_baseline.txt conflicts on each merge. The
  resolution: always fetch fresh, measure `current_count()`, and set the
  baseline to that exact number. Do not carry a cached measurement.
- **Push slot contention**: The flock-based push_any_slot.sh script silently
  died when all slots were held. Direct flock on slot 0 (blocking) is more
  reliable than the multi-slot script when the fleet is fully loaded.
- **Stale test timestamp**: The `test_renew_on_own_live_lease_extends_ttl`
  test used `_NOW` (a fixed 2026-06-19 timestamp) for a lease that `main()`
  would evaluate against the real clock. Fixed by using `datetime.now(UTC)`
  relative to the real clock, matching the pattern used by `_live_held_body`.

### Overturned premises

- The issue briefing implied \#4375 SHA defect was unaddressed. origin/main
  already had `_pr_head_sha()` fetching from GitHub REST. The remaining
  defect was the auth fail-open, which was real.
- `renew` does not need new protocol logic: `classify_acquire` already
  handles self-renewal when the caller's `acting_author` matches the lease
  author. `renew` is just a named entry point.
- \#4377 race cannot be fixed in code because `set_pr_auto_merge.py` already
  has `disable_auto_merge()`. The fix is operational: the protocol
  instructions in `pr-autofix.md` had no step to disable before resolving
  the final thread. Fixed there.

## Mutation Table

| Mutation | Killing Test | Notes |
|----------|-------------|-------|
| Remove `except SystemExit` from `main()` | `test_auth_failure_exits_zero_act`, `test_auth_failure_on_status_exits_zero_act`, `test_auth_failure_on_release_exits_zero_act`, `test_repo_resolution_failure_exits_zero_act` | 4 tests kill this mutation |
| Remove `renew` from `_run_command()` routing | `test_renew_on_own_live_lease_extends_ttl`, `test_renew_on_free_lease_re_claims`, `test_renew_returns_skip_when_held_by_other` | 3 tests kill this mutation |
| Cosmetic: blank line in module docstring | (none killed it) | Survived, confirming harness correctness |
