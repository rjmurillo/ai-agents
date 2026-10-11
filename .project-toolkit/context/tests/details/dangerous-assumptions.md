## Dangerous assumptions

- `check_nested_tests.py` does not scan every test file, and not by depth: helpers not named `test_*.py` (`tests/hook_test_helpers.py`, `tests/ci/ratchet_test_helpers.py`) are never opened.
- `checks_coverage.py` is not a coverage gate; it wraps the advisory `/review`-marker check. Real 100% pins: `coverage report --fail-under=100` steps in `pytest.yml`.
- "My push ran the suite" is false: pre-push runs only testmon-selected tests; misses subprocess-only code. CI runs all.
- `tests/evals/*-scenarios.json` are pytest input, not just `scripts/eval/` corpora. `tests/eval/test_eval_prompt_change.py::TestShippedScenariosValid` requires 2+ `verdict_options` each; sibling contract tests pin critic, qa, orchestrator and spec scenario IDs.
