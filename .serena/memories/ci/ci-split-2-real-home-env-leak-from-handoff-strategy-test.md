# pytest flake: an in-process eval CLI leaked EVAL_RUNTIME_REAL_HOME (fixed in #7401)

## Symptom

The `[claude]` cases of `tests/eval/test_cli_credential_transports.py` failed in CI.
They passed alone and passed locally. The failure looked unrelated to the PR's diff.
PR #7387 saw it on `pytest (split-2)`. PR #7401 says Seed testmon was red on main from #7385 on.

## Cause

The handoff, control-ablation, and runtime-parity CLIs set `EVAL_RUNTIME_REAL_HOME=1` for `--real-home`.
They wrote `os.environ` directly and did not restore it.
Tests call these CLIs in process, so the flag stayed set for later tests on the same worker.
`tests/eval/test_handoff_strategy_transient.py::TestProvenanceOrder::test_runner_state_is_taken_before_the_first_launch` was one such test.
With the flag set, the Claude CLI helpers skip their HOME relocation and credential lookup (`scripts/eval/_claude_cli.py` lines 127, 191, and 216).
The credential tests expect the relocation, so they failed.
Whether it failed depended on which tests shared a worker, so it showed up as a flake.

## Fix

PR #7401 (`255ccf59f`, 2026-11-16) added the context manager `temporary_real_home` in `scripts/eval/_isolated_claude_login.py`.
It sets the flag for the call and restores the old value on return or on an error.
All three CLIs now use it: `eval_handoff_strategy.py` line 258, `eval_control_ablation.py` line 404, `eval_runtime_parity.py` line 1138.

## Lesson

A CLI that tests call in process shares the test process environment.
If it sets an environment variable, it has to restore it, or every later test on that worker inherits it.
`monkeypatch.setenv` in the test is the other guard, since monkeypatch restores the value at teardown.

## Evidence

- [2026-11-16] [orchestrator session, PR #7387]: split-2 failed twice on the `[claude]` cases.
- [2026-11-16] Probe: run one test in process with `pytest.main`, then read `os.environ`.
  - At `2e98e526a`, before #7401, the test above left `EVAL_RUNTIME_REAL_HOME=1`.
  - After merging `255ccf59f`, the same probe left it unset.

## Relations

- **related_to**: [ci/pytest-split-cache-freeze-repeats-timeout](pytest-split-cache-freeze-repeats-timeout.md)
