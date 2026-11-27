## Dependencies

- Feeds `pytest.yml` `zero-collection-guard` (blocking, no `needs:`/`if:`) and 8-leg matrix (never `check-paths`-gated).
- Other workflows run named test files (grep below); `claude.yml` runs `tests/workflows/test_claude_authorization.py` via `check_claude_authorization.py --checker`.
- `lefthook.yml` pre-push omits `python-tests` and `zero-collection-tests` (ADR-104 2026-11-26); CI `pytest.yml` is the gate.
- Pre-PR gate registry: `scripts/AGENTS.md`. Template drift/parity: `build/AGENTS.md`.
