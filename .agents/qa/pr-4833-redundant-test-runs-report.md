---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-10-session-10034.json
qaCommit: f9243b90334f6d176099ea79a0c1e96aadfb1498
---

# Issue #4826 redundant test-run removal validation

## Scope

Implementer self-validation through commit
`f9243b90334f6d176099ea79a0c1e96aadfb1498`
against the acceptance criteria in Issue #4826. Independent qa/critic review
is still recommended before merge; this report documents the evidence
gathered during implementation, it does not replace that review.

## Result

PASS. Both files still make every assertion they made before the change, at
measured lower subprocess cost, and every mutant/isolation/inverted-control
contract named in the issue is unchanged.

## Evidence

- `tests/mutation/test_mutate_debate_log_path.py` BEFORE (this machine,
  `uv run --frozen python -m pytest ... -q --tb=short --durations=0`):
  5 passed in 195.39s. Per-test: M1 54.37s, M3 53.07s, M2 52.80s, IC 29.95s,
  isolation 1.00s.
- Same file AFTER: 5 passed in 110.72s. Per-test: M1 26.94s, M3 26.46s,
  M2 26.24s, IC 26.22s, isolation 0.94s. Savings ~84.67s (~43%). Test count
  unchanged.
- `tests/test_skill_bundle_suites_run.py` BEFORE: 8 passed in 27.43s.
  suite_passes[.claude/skills] 7.58s, suite_passes[src/copilot-cli/skills]
  7.18s, collects_tests[.claude/skills] 6.34s,
  collects_tests[src/copilot-cli/skills] 6.22s (4 distinct `_run_tree`
  subprocess invocations).
- Same file AFTER: 8 passed in 12.46s. Only 2 `_run_tree` subprocess
  durations reported (suite_passes[.claude/skills] 6.48s,
  suite_passes[src/copilot-cli/skills] 6.16s); the `collects_tests` cases
  reuse the cached `CompletedProcess`. Savings ~14.97s (~55%). Test count
  unchanged.
- Broader regression check: `uv run --frozen python -m pytest
  tests/mutation/ tests/test_skill_bundle_suites_run.py -q --tb=short`:
  26 passed in 154.05s, covering every mutation-harness file in the
  directory (baseline-ratchet, debate-log-path, lefthook-ratchet-wiring,
  pr-description, validate-findings-scope) plus the skill-bundle suite file.
- `uv run --frozen ruff check` and `ruff format --check` on both changed
  files: all checks passed, both already formatted.
- `uv run --frozen python scripts/validation/pre_pr.py --quick`: RESULT
  All validations passed (46 passed, 0 failed, 4 skipped by `--quick`).

## Contract mapping (Issue #4826 acceptance criteria)

- Mutant-kill contract: `test_m1_*`, `test_m2_*`, `test_m3_*` still call
  `_apply_positive_mutant`, which applies the mutant and asserts
  `result.returncode != 0` via one `_run_tests_in` subprocess run each.
  Unchanged.
- Active-target-diff contract: each mutant test still calls
  `_active_target_unmodified()` (the pre-existing git-diff check for the
  active worktree), and `_apply_positive_mutant` now also asserts
  `wt_target.read_bytes() == original` as a cheap byte comparison proving
  the scratch worktree's target file was restored, replacing the deleted
  subprocess restore-check.
- Isolation contract: `test_scratch_worktree_created_and_removed` is
  byte-for-byte unchanged.
- Inverted-control contract: `test_ic_comment_only_change_survives` is
  byte-for-byte unchanged (one subprocess run, asserts `rc == 0`).
- Bundle-pass contract: `test_bundle_tree_suite_passes` still fails if any
  bundle suite under a root fails (`result.returncode == 0` assertion
  unchanged; `result` now comes from the memoized `_run_tree`).
- Collection contract: `test_bundle_tree_collects_tests` still fails if a
  root's run collects zero tests (`"passed" in result.stdout` assertion
  unchanged).
- Each configured root's bundle suite subprocess executes at most once per
  pytest session: `_run_tree` is decorated with `@functools.cache`, keyed
  on the hashable `Path` argument.

## Risks / follow-ups for reviewer

- `functools.cache` has no invalidation hook. Within a single pytest
  session this is correct (repo state does not change mid-run), but a
  reviewer should confirm no other test in the same session mutates the
  bundle tree contents between the two consuming tests. No such test was
  found in this file or its imports.
- The mutation file is 323/500 lines per the taste-lint file-size advisory
  (pre-existing warning, not introduced by this change; it triggered
  because the file was already near the threshold and the byte-comparison
  addition added a few lines). Advisory only, not blocking.
