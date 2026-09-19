## Dependencies

- Feeds `pytest.yml`'s `zero-collection-guard` (blocking, no `needs:`/`if:`) and its 5-leg matrix, gated by `check-paths` from `scripts/test_selection/path_policy.yml`; `select_tests.py` reads it locally.
- Other workflows run named test files (grep below), so a rename reds a check the path filter never shows; `claude.yml` runs `tests/workflows/test_claude_authorization.py` as `scripts/ci/check_claude_authorization.py --checker`.
- `lefthook.yml` pre-push expensive stage: `python-tests` (15m, `AI_AGENTS_PYTEST_WORKER_CAP=4`), `zero-collection-tests` (4m), both ignore the path filter.
- Pre-PR gate registry and flags: `scripts/AGENTS.md`. Template-drift and parity semantics: `build/AGENTS.md`.
