## Dependencies

- Feeds `pytest.yml`'s `zero-collection-guard` (blocking, no `needs:`/`if:`) and the 8-leg matrix, which `check-paths` never gates.
- Other workflows run named test files (grep below), so a rename reds a check the path filter never shows; `claude.yml` runs `tests/workflows/test_claude_authorization.py` as `scripts/ci/check_claude_authorization.py --checker`.
- In `lefthook.yml`, `python-tests` (15m) uses a scaled cap and reserves 3 CPUs. Both it and `zero-collection-tests` (4m) ignore the path filter.
- Pre-PR gate registry and flags: `scripts/AGENTS.md`. Template-drift and parity semantics: `build/AGENTS.md`.
