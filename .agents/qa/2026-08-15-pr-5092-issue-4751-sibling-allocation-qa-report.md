# QA Report: PR #5092, Issue #4751 sibling-branch session-number allocation

**Date**: 2026-08-15
**Session**: 2026-08-15-session-99916 (`.agents/sessions/2026-08-15-session-99916-b5147e7a0-fix-issue-4751-session-number.json`)
**Branch**: `claude/issue-4751-session-number-siblings`
**Scope**: `.claude/skills/session-init/session_init/allocation.py`, `new_session_log.py`, `new_session_log_json.py`, copilot-cli mirrors, ratchet baselines, root-skip test guards.

## Acceptance criteria verification

| Criterion | Verdict | Evidence |
|-----------|---------|----------|
| Allocation consults unmerged sibling branches, not origin/main alone | PASS | `sibling_refs_max_session` walks `refs/remotes/origin/*`; integration test `test_unmerged_sibling_number_is_not_reused` builds a real origin whose sibling branch holds session 2340 unmerged and asserts allocation returns 2341 |
| Positive: collision with a sibling branch detected/avoided | PASS | `test_detects_number_taken_on_unmerged_sibling` (unit, refs at 10003/10004) and the real-git integration test above |
| Negative: no false collision when siblings share no numbers | PASS | `test_no_false_collision_when_siblings_share_no_numbers` (scan reports exactly main's max) and `test_no_false_collision_when_sibling_adds_nothing` (real git, sibling ref deleted, allocation returns 2336) |
| Edge: probe failure is failure, not absence | PASS | Enumeration failure, per-ref failure, timeout, and budget expiry all return `None` (5 unit tests); `test_outside_any_repo_is_probe_failure_not_absence` pins `None` outside a repo; `test_complete_scan_with_no_sessions_returns_zero_not_none` pins the absence reading as `0`; `test_absence_is_evidence_and_does_not_fall_back` pins that fallback fires on failure only |
| Naming validators unaffected | PASS | Filename scheme untouched; `validate_session_json.py` passed on the session log created by the modified allocator (`--creation-mode`, `[PASS] Session log is valid`) |
| Both creator scripts routed through one policy | PASS | `new_session_log.py` via `_remote_max_session`; `new_session_log_json.py` via `remote_max_session` (wiring tests `test_auto_detect_avoids_number_taken_on_remote_ref`, `test_ceiling_includes_remote_max`) |

## Test evidence

- `tests/skills/session/` (test_sibling_allocation.py 19, test_new_session_log.py 39, test_new_session_log_json.py 16, plus siblings): 162 passed.
- Wider session surface (`tests/skills/test_session_scripts.py`, `tests/test_session_date_end_to_end.py`, skill-bundle `test_session_init.py`): 250 passed.
- Full pre-push suite (`git_hook_policy.py pytest`): green on the final push (28,857+ passed; the 24 pre-existing failures traced to container gaps and two ratchet entries, all resolved in-branch)
- `uv run python scripts/validation/pre_pr.py`: RESULT: All validations passed.
- Runtime (dogfood): this session's own log was created through the new scan; 241 remote refs walked in 1.03s, sibling reading agreed with origin/main at 99915, allocated 99916.

## Gate repairs required to get the pre-push suite green in this container

1. Guard-corpus baseline: occurrence 1 of `result = subprocess.run(` in `new_session_log.py` deliberately removed (call moved to `allocation.py`, which pins `encoding="utf-8"` so no new finding).
2. Skill-portability ratchet: one grandfathered ref moved between files; net debt unchanged (158 refs).
3. Two chmod-based permission tests lacked the repository's existing root-skip idiom and fail on pristine origin/main in root containers; the established `skipif` guard was applied (`tests/test_lefthook_integration.py`, orphan-ref-validator `test_scan.py`).
4. `sync_observations` (pre-push `observation-sync-advisory`) gained an internal 200s budget with per-child clamping: with forgetful unreachable, 30+ observation files in one push outlived the 5m lefthook cap, and the cap kill is the one failure the advisory contract cannot absorb (killed at 300.87s and 303.55s on this branch). Security agent reviewed the hunk: APPROVE, required clamp fix and both LOW findings incorporated. Five tests pin the behavior, including the budget-plus-child-under-cap invariant.
5. Container gaps repaired (not repo changes): `sqlite3` CLI and `openssh-client` installed; 17 pre-existing failures on origin/main traced to their absence.

## Residual risk

- Two branches allocating before either pushes can still collide on the number; the #4561 filename discriminator keeps their filenames from colliding. The issue names the pushed-but-unmerged window as the normal case; that window is closed.
- The sibling scan sees only refs the clone has fetched. A single-branch shallow clone sees fewer siblings; the reading is still complete over what exists locally, and the origin/main fallback path is unchanged.
