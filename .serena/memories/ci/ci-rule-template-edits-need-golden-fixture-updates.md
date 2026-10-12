# A templates/rules edit also needs its golden fixture, and local gates miss it

## What happened

PR #6316 edited `templates/rules/ci-scripts.md` and `templates/rules/plugin-self-containment.md`, ran `build_all.py`, and passed `pre_pr.py` and the pre-push hook. CI job "pytest (split-1)" then failed six tests in `tests/build_scripts/test_rule_templates_lossless.py` (three per rule: template render, committed `src/claude` copy, binplaced `.claude` copy).

## Cause

That test compares each rule to a byte-exact copy under `tests/build_scripts/fixtures/rule_templates_b2/expected/<name>.md`. `build_all.py` does not write the fixtures. The module docstring says so: the fixture is an independent pin.

## Fix

Copy the edited template over its fixture file, then run the test (86 passed after the copy). The agent-prompt equivalent is `tests/build_scripts/fixtures/agent_templates_b1/expected/`, checked by `test_agent_templates_lossless.py`.

## Why it slipped past local runs

`pre_pr.py` does not run this test. The pre-push pytest leg selects tests with testmon, which can skip it (see `ci/ci-local-push-and-test-environment-contracts`). CI runs the full suite.

## Sources

- `tests/build_scripts/test_rule_templates_lossless.py` lines 1 to 8.
- CI job 114715447079 log on PR #6316.
