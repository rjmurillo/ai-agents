## Dependencies

- Feeds `pytest.yml`'s `zero-collection-guard` (blocking, no `needs:`/`if:`) and the 8-leg matrix, which `check-paths` never gates.
- Other workflows run named test files (grep below), so a rename reds a check the path filter never shows; `claude.yml` runs `tests/workflows/test_claude_authorization.py` as `scripts/ci/check_claude_authorization.py --checker`.
- `lefthook.yml` pre-push omits `python-tests` and `zero-collection-tests` (ADR-104, 2026-11-26); CI `pytest.yml` is the gate.
- Pre-PR gate registry and flags: `scripts/AGENTS.md`. Template-drift and parity semantics: `build/AGENTS.md`.
