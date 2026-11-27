## Dangerous assumptions

- `check_nested_tests.py` ignores helpers not named `test_*.py` (`tests/hook_test_helpers.py`, `tests/ci/ratchet_test_helpers.py`).
- `checks_coverage.py` wraps advisory `/review`-marker check, not coverage. Real 100% pins: `coverage report --fail-under=100` in `pytest.yml`.
- "My push ran the suite" is false: pre-push does not run pytest (ADR-104 2026-11-26). Run targeted `uv run pytest <paths>` locally; CI runs all legs.
- `tests/evals/*-scenarios.json` are pytest input (`test_eval_prompt_change.py::TestShippedScenariosValid` requires 2+ `verdict_options`; sibling tests pin critic/qa/orchestrator/spec IDs).
