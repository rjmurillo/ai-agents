## Entry points

- `git_hook_policy.py pytest`: on-demand local `pytest --testmon` wrapper (not in pre-push per ADR-104 2026-11-26).
- `AI_AGENTS_PYTEST_FULL_SUITE_LOCALLY=1`: 4 local partitions, no testmon; CI runs 8 legs (`split-1`..`6`, `safe-push`, `pr-autofix`).
- `check_zero_collection_tests.py`: catches zero-collecting `test_*.py` (CI `zero-collection-guard` runs unconditionally).
- One leg: `uv run python scripts/ci/run_pytest_partition.py --partition split-1`. Timings from Actions cache `pytest-split-durations-` (saved on main pushes; fallback splits by count). `duration_gate_check.py` fails main on repeat leg >480s; PRs and 1.5x spread warn.
