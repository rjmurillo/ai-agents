## Dangerous assumptions

- `check_nested_tests.py` does not scan every test file, and not by depth: helpers not named `test_*.py` (`tests/hook_test_helpers.py`, `tests/ci/ratchet_test_helpers.py`) are never opened.
- `checks_coverage.py` is not a coverage gate; it wraps the advisory `/review`-marker check. Real 100% pins: `coverage report --fail-under=100` steps in `pytest.yml`.
- "My push ran the suite" is false by default: without `AI_AGENTS_PYTEST_FULL_SUITE_LOCALLY=1` a push runs an import-graph subset or only collects, asserting nothing.
- `tests/evals/*-scenarios.json` are pytest input, not just `scripts/eval/` corpora. `tests/eval/test_eval_prompt_change.py::TestShippedScenariosValid` requires 2+ `verdict_options` each; sibling contract tests pin critic, qa, orchestrator and spec scenario IDs.
