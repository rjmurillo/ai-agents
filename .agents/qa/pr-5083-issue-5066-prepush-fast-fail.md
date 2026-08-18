---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-15-session-5066-prepush-fast-fail.json
qaCommit: a5c1c5ede90699a5f9e45946730c591e3835ad78
---

# QA Report: pre-push fast-fail staging (issue #5066)

- **Branch**: `claude/issue-5066-prepush-fast-fail`
- **Session log**: `.agents/sessions/2026-08-15-session-5066-prepush-fast-fail.json`
- **Scope**: `lefthook.yml` pre-push restructure, `tests/test_lefthook_integration.py` pin update, new `tests/ci/test_lefthook_prepush_fast_fail.py`

## What changed

`lefthook.yml` pre-push is restructured into a fast-fail stage (cheap blocking
gates) that must pass before the expensive stage (python-tests, semgrep, mypy,
workflow-local-run, build-all-check, e2e smokes, pre-pr-validation) starts.
Every job body is byte-identical to the previous config; only positions
changed, verified by parsing both configs and diffing per-job mappings
(36 jobs on both sides, zero body diffs, zero added or removed names).

## Acceptance criteria verification

### A failure detectable in under 60 seconds never costs a full pytest run

The hook is `piped: true`, so a failing entry skips everything after it.
Verified empirically on lefthook 2.1.10 in a fixture repository: a failing job
inside a `parallel: true` group makes every later top-level entry report
`(skip) broken pipe`, and the expensive marker job never ran.
`tests/ci/test_lefthook_prepush_fast_fail_runtime.py::TestRuntimeFastFail` pins
this against the real binary with a positive control. (The runtime suite split
out of `test_lefthook_prepush_fast_fail.py` into its own module to hold the
500-line file-size taste rule; see the round-2 spec-validation response below.)

Fast-stage gates and their measured standalone wall clocks (2026-08-15, idle
machine): taste-count-ratchet 2.5s, type-ignore 0.1s, memory-index 0.4s,
cli-exit-contract 10.0s, memory-index-token 1.5s, ruff_ratchet 0.1s,
ruff_count 0.4s, merge-tree 16.6s, unreachable-statements 5.2s, branch-scope
0.2s, branch-context 0.2s, path-normalization 1.7s, planning-artifacts 0.1s,
review-axis-drift 0.1s, retrospective-policy 0.2s. Parallel-stage maximum is
about 17s; the fast stage also carries less contention than before because it
no longer shares a scheduling group with pytest.

### Total wall time for a clean push not worse by more than 10 percent

Before: stdin piped group (including semgrep) ran serially, then one parallel
group whose maximum is python-tests (measured 741.85s per
`.serena/memories/ci/run-count-ratchets-before-the-expensive-pre-push.md`).
After: the same stdin group minus semgrep, plus the fast parallel stage
(max about 17s standalone), then semgrep serial (position relative to the
expensive group unchanged: it ran before that group in both configs), then
the same expensive parallel group. The only wall-clock addition on a clean
push is the fast parallel stage maximum, roughly 17s against a 12-to-17
minute total, about 2 percent. The real push of this branch exercised the
new hook end to end (see Evidence).

### All existing gates still run; only ordering changes

Per-job diff against `origin/main:lefthook.yml`: 36 jobs before and after,
no additions, no removals, no run/glob/env/timeout/use_stdin changes.
`security-scan` stays a serialized stdin consumer (top-level job of the piped
hook rather than member of the piped group), preserving ci-scripts.md MUST-21:
a fixture run confirmed a top-level `use_stdin: true` job placed after groups
receives the byte-identical full ref-update payload. The two e2e jobs keep
their pre-existing `use_stdin`-inside-parallel-group shape, unchanged and now
pinned as a closed exception list so it cannot silently grow.

## Test evidence

- Current state, eight lefthook-pinning modules (`test_lefthook_prepush_fast_fail.py`, `test_lefthook_prepush_fast_fail_runtime.py`, `test_lefthook_integration.py`, `test_lefthook_config_integrity.py`, `test_lefthook_ratchet_wiring.py`, `test_worktree_gc_wiring.py`, `test_lefthook_gate_config.py`, `test_pre_pr_runs_lefthook_ratchets.py`): 947 passed, 1 skipped (the skip is a root-guarded permission test in this root container; it runs in non-root CI). Repeated three times under full-selection contention with identical results, plus a 30-run stress loop of the runtime module (30/30 green) after fixing a read-modify-write race in the fixture's marker script (two parallel fixture jobs could lose a log line; now an atomic O_APPEND write).
- History: an earlier run of this suite reported 1 failed. That failure, `test_the_tracked_scan_fails_config_on_an_unreadable_file`, also failed on the unmodified origin/main tree in this environment (root reads chmod-000 files) and is now skipped-by-guard here. The full pre-push pytest run surfaced two more of the same class (claude-mem get_count error path, orphan-ref-validator auth exit code); all three carry the repository's established root skipif (`getattr(os, "geteuid", lambda: -1)() == 0`, the guard tests/test_agent_registry.py and ten other modules already use), with the skill-test mirror regenerated by the build pipeline. They still run in CI, which is non-root.
- Runtime coverage now exercises both fast-stage halves: a failing job in the parallel half and a failing job in the piped stdin half each skip every later entry (semgrep, pytest analogues never run), and the positive control delivers a multi-line two-ref stdin payload byte-identical to both serialized consumers, the in-group gate and the late top-level job standing in for security-scan.
- Negative controls: the new ordering tests fail against the origin/main config (taste-count-ratchet and python-tests shared entry index 4, security-scan sat at index 3 before the ratchets), so the pins discriminate the old shape from the new one.
- New coverage is positive (ordering holds, runtime clean-run control), negative (misordered synthetic config detected, stdin-in-parallel synthetic config detected, runtime fast-stage failure skips the expensive stage), and edge (unknown job name, config without pre-push, duration unit parsing, fast-stage timeout ceiling).

## Merge with main (round 4)

Main advanced twice during review (through commit `2a04b4bd8`, eight commits).
Two merges were required; the second carried a real functional conflict, not a
cosmetic one: PR #5088 (merged to main) retired the standalone
`build-all-check` pre-push job, folding its `build_all.py --check` into
`pre-pr-validation`'s new Generated Artifact Staleness gate, because two
concurrent unlocked `build_all --check` invocations in the same parallel group
raced their snapshot/restore over the same owned prefixes. My branch had moved
`build-all-check` into the expensive stage rather than deleting it, so the
merge conflicted. Resolved by taking main's deletion: removed the job from
`lefthook.yml`, from `EXPENSIVE_JOBS` in the fast-fail test module, and updated
the module's docstring to explain why. `tests/test_lefthook_integration.py`
had already been updated by main's own PR to assert `build-all-check` is
absent; that assertion merged cleanly and now passes. A second merge also
picked up main's `PRE_PR_OUTER_CAP_SECONDS: "900"` addition to
`pre-pr-validation`'s env, preserved on the (moved) expensive-stage copy. A
third conflict deduplicated a `memory-index.md` add/add collision where both
branches independently indexed the same two memory files with different token
counts; resolved to one row per file with the correct current count.

Post-merge verification: job-name set diff between the merged tree and
`origin/main` is empty in both directions (35 jobs each); 1061 passed, 1
skipped across the ten lefthook/build_all test modules; taste count ratchet OK
(583); merge-tree-ratchet OK against `origin/main`.

## Spec-validation response (PR #5083)

Round 3: the expensive parallel group is now exact-pinned too
(`EXPENSIVE_STAGE_ROSTER`), closing the validator's finding that a job added
after security-scan was auto-accounted without a roster decision; every
pre-push placement now requires editing a roster constant. The two remaining
PARTIAL residuals are deliberate scope boundaries: the dash guard split is
issue #5086, and an automated wall-clock budget gate would be new
functionality outside this issue's "only ordering changes" criterion (a CI
wall-clock threshold is also inherently machine-sensitive; see the MUST-16
caveat below).

The AI spec validation returned PARTIAL with two pin-strength findings, both
addressed: the fast-stage rosters are now exact two-way membership pins with a
complement test (a new pre-push job cannot land in any stage without a roster
decision), and the timeout ceiling splits per stage half (5m parallel, 10m
stdin group), matching the largest cap each half already carries. The dash
guard gap is tracked as issue #5086: promoting it stays out of this PR because
the issue's own acceptance criteria forbid adding or re-scoping jobs. The
requested controlled before/after clean-push A/B is not reproducible from this
branch (the before-config no longer exists on it); the comparison stands on
the measured historical baseline (`python-tests` 741.85s, 12-17 minute
envelope) against this branch's measured 11-minute clean push.

## Merge with main (round 5)

Main advanced one more commit during review: `d76f21dec` (PR #5039, re-pin
worktree identity before the pr-autofix cleanup commit, plus a new
`Placeholder Identity Check` workflow). `git merge --no-edit origin/main`
resolved with the `ort` strategy and zero conflicts; the changed files
(`worktree_identity.py` in three mirrored locations, the new
`placeholder-identity-check.yml` workflow, `scripts/ci/determine_placeholder_range.py`,
`scripts/invoke_batch_pr_review.py`, `scripts/quality_gate/consume_pytest_signal.py`,
and their tests) do not overlap this PR's `lefthook.yml` restructure or its
new test modules.

The `sync_observations` 240s wall-clock budget and the root-guard skipif fixes
cited when this merge was requested were already present on this branch from
round 4 (`_OBSERVATION_SYNC_BUDGET_SECONDS = 240.0` in
`scripts/validation/git_hook_policy.py`, unchanged by this merge; verified with
`git diff HEAD origin/main -- scripts/validation/git_hook_policy.py` before the
merge, which reported no diff in that file). No hunks needed resolving toward
main in that area because there was no overlap to resolve.

Post-merge verification: job-name set diff between the merged tree's
`lefthook.yml` pre-push and `origin/main:lefthook.yml` is empty in both
directions (35/35); 997 passed, 1 skipped across the ten lefthook and
worktree-identity test modules (`test_lefthook_prepush_fast_fail.py`,
`test_lefthook_prepush_fast_fail_runtime.py`, `test_lefthook_integration.py`,
`test_lefthook_config_integrity.py`, `test_lefthook_ratchet_wiring.py`,
`test_worktree_gc_wiring.py`, `test_lefthook_gate_config.py`,
`test_pre_pr_runs_lefthook_ratchets.py`, `test_pr_autofix_worktree_identity.py`,
`test_invoke_batch_pr_review.py`).

## Known gaps

- The dash guard and QA-report discovery named in the issue body live inside
  `pre-pr-validation` (`checks_dash.validate_dash_prohibition`) and
  `session-json-validation` (`validate_qa_report_evidence`). The session-log
  and QA checks run in the fast stdin group; the dash guard rides
  `pre-pr-validation` (measured 75.86s), which stays in the expensive stage
  because promoting it would add its full wall clock to every clean push.
  Splitting the dash check into a standalone fast job would add a new job,
  which the issue scopes out ("only ordering changes").
- Fast-stage timings were measured standalone on one machine (ci-scripts.md
  MUST-16 caveat). The stage's job timeouts are unchanged (2m-10m caps), so a
  loaded machine degrades wall clock, not correctness.
