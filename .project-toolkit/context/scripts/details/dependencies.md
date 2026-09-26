## Dependencies

- Plugin lib source: `scripts/{github_core,hook_utilities,ai_review_common}`, `hook_utilities/bootstrap.py`, `validation/validate_review_marker.py`; `build_all.py` (`build/scripts/lib_mirror.py`) renders them into both plugin lib trees and binplaces the claude side (ADR-109 B5). `sync_plugin_lib.py` is a deprecated shim; add no caller.
- `lefthook.yml` calls `scripts/validation/`, `scripts/maintenance/`, `-m scripts.testing.mutation_workspace`, and top-level `scripts/*.py`; never `scripts/ci/` or `scripts/eval/`.
- `.github/workflows/*.yml` call `scripts/ci/`, `scripts/validation/`, `scripts/workflows/`, `scripts/eval/`, `scripts/metrics/`, `scripts/maintenance/`, `scripts/testing/`; `pytest.yml` reads `scripts/test_selection/path_policy.yml` as its paths filter.
- `scripts/metrics/kill_criteria.py` is invoked by a bare interpreter in `drift-detection.yml`: stdlib only.
- `scripts/memory/`: documented in `.serena/memories/README.md`; no skill and no hook call it (only `tests/`). Live checks: `.claude/skills/memory/scripts/test_memory_health.py`, `test_memory_size.py` (`git_hook_policy.py memory-size`).
- Repo-root `memory_enhancement` symlink -> `scripts/memory_enhancement/`; edit the target.
