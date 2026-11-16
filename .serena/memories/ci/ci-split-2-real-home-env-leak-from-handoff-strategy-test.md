# pytest split-2 flake: an eval test leaks EVAL_RUNTIME_REAL_HOME

## Symptom

CI `pytest (split-2)` fails on the `[claude]` cases of `tests/eval/test_cli_credential_transports.py`.
The same tests pass alone and pass locally. The failure looks unrelated to the PR's diff.

## Cause

`tests/eval/test_handoff_strategy_transient.py::TestProvenanceOrder::test_runner_state_is_taken_before_the_first_launch` passes `--real-home`.
`eval_handoff_strategy._run_live` then writes `os.environ[REAL_HOME_ENV] = "1"` directly (`scripts/eval/eval_handoff_strategy.py` line 259).
The test does not call `monkeypatch.setenv` for that variable, so pytest does not restore it.
Every later test in the same worker sees `EVAL_RUNTIME_REAL_HOME=1`.
With that flag set, the Claude CLI helpers skip their HOME relocation and credential lookup.
The check is `_real_home_requested()` (`scripts/eval/_claude_cli.py` line 127). The skips are at lines 191 and 216.
The credential transport tests expect the relocation, so their `[claude]` cases fail.
Whether it fails depends on how the split puts tests in one worker, so it shows up as a flake.

## Fix (not applied as of 2026-11-16)

Add `monkeypatch.setenv(REAL_HOME_ENV, "1")` at the top of that test.
Then monkeypatch removes the variable at teardown.
The helper `run()` in the same file already does this (line 72).

Other tests pass `--real-home` to `eval_handoff_strategy.main` too, such as `TestStartRepeat`.
They do not leak today because `main` refuses them before it calls `_run_live`.
A new test that reaches `_run_live` with `--real-home` would leak the same way.
`eval_runtime_parity.py` line 1135 and `eval_control_ablation.py` line 402 use the same direct write.
Any test that drives them with `--real-home` needs the same guard.

## Evidence

- [2026-11-16] [orchestrator session, PR #7387]: split-2 failed twice on the `[claude]` cases. Line references read on `origin/main` at `2e98e526a` (2026-11-16).
- [2026-11-16] Probe at `2e98e526a`: run one test in process with `pytest.main`, then read `os.environ`.
  - `test_runner_state_is_taken_before_the_first_launch` left `EVAL_RUNTIME_REAL_HOME=1`.
  - `TestStartRepeat` (3 cases) and `TestCli::test_more_than_three_repeats_is_refused_before_any_launch` left it unset.
- The fix was recorded in the PR #7387 body and left out of that PR as out of scope.

## Relations

- **related_to**: [ci/pytest-split-cache-freeze-repeats-timeout](pytest-split-cache-freeze-repeats-timeout.md)
