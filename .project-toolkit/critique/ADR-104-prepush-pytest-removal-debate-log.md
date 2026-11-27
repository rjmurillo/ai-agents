# ADR Debate Log: ADR-104 Amendment (2026-11-26): Remove Local Pre-Push Pytest and Isolate Unused-Dependency Checks

Prior debate log: `.project-toolkit/critique/ADR-104-debate-log.md`
Claims ledger: `.project-toolkit/critique/ADR-104-prepush-pytest-removal-claims-ledger.md`
Empirical analysis: `.project-toolkit/analysis/host-contention-2026-11-26.md`
Target ADR: `.project-toolkit/architecture/ADR-104-gate-tier-placement-and-budgets.md`

## Summary

- **Rounds**: 2
- **Review Panel**: 6 independent seats (`architect`, `critic`, `independent-thinker`, `analyst`, `security`, `high-level-advisor`)
- **Final Verdict**: **Accepted** (6-0 unanimous `Accept` in Round 2; 0 open P0, P1, P2, or `REFUTED` claims)
- **Scope**: ADR-104 Amendment 2026-11-26 removing `python-tests` and `zero-collection-tests` from `lefthook.yml` `pre-push`, isolating `validate_unused_dependencies` in `scripts/validation/checks_ci_parity.py` with `uv run --isolated --frozen --extra dev --extra eval`, and updating affected budget/wiring/doc/template artifacts while preserving on-demand local `pytest`, `git_hook_policy.py pytest`, `check_zero_collection_tests.py`, and CI `pytest.yml` gates.

## Round 1

### Agent Positions (Round 1)

| Agent | Position | Core Objection / Key Finding |
|-------|----------|------------------------------|
| architect | Block | ADR-104 exceeded the 1,000-line lifecycle size cap (1,073 lines); Decision section still read as keeping `python-tests` on pre-push; stale `pytest.yml:262-265` citation; missing top-level `## Amendment 2026-11-26` heading and frontmatter date update; clamped count and sunset trigger needed repair. |
| critic | Block | Clamped/unclamped job count misstated as `12 clamped, 14 unclamped` instead of `13 clamped, 14 unclamped = 27`; `CONTRIBUTING.md` still referenced `pre-push` pytest and lacked `--isolated`; Revert Path omitted concrete files; `C8` and `test_zero_collection_guard_wiring.py` docstring needed alignment. |
| independent-thinker | Block | Missing counterfactual separating Fix A (`--isolated` venv fix) from Fix B (pre-push removal under structural multi-worktree contention); missing `--isolated` runtime and offline failure-mode measurements; `zero-collection-tests` whole-tree collection rationale needed quantification; quarterly `testmon-seed` sunset trigger lacked telemetry. |
| analyst | Block | Clamped count off by 1 (`13 clamped, 14 unclamped = 27`); live declared pre-push budget (`3330s / 55.5 min`) conflated with baseline ceiling (`3450s / 57.5 min`); stale line numbers (`pytest.yml:262-265`, `CODEOWNERS:61`); `.github/dependency-hygiene/policy.toml:23` lacked `--isolated`; `python-check` advisory note missing. |
| security | Accept | No new attack surface or weakened merge control, with P1 to document pre-existing ADR-101 P0/P1/P2 enforcement boundaries (`ruleset_params_baseline.json`, head-editable workflow on `pull_request`, path-filtered `security` and `test-windows-pwsh` outside `test-result`) and P2s for cleanup command, citations, and time-boxed review. |
| high-level-advisor | Accept | Strategic direction sound; P1s to replace the unmeasurable `testmon-seed` sunset trigger with a concrete date, add Chesterton's Fence counterfactual separating Fix A from Fix B, and fix stale `pytest.yml:262-265` citations. |

### Round 1 Findings and Resolution

- **P0-1 (ADR-104 lifecycle size cap):** Trimmed historical prose without losing historical rationale, bringing `.project-toolkit/architecture/ADR-104-gate-tier-placement-and-budgets.md` to 816 lines (`<= 1,000` cap; `scripts/validation/check_adr_lifecycle.py` passes with `size-cap` improved to `67/70`).
- **P0-2 (Decision coherence and amendment structure):** Updated frontmatter `date: 2026-11-26`, reconciled `Status`, `What ships`, and `Decision` to mark `Current (2026-11-26 amendment)` vs. historical on-demand behavior, and added a top-level `## Amendment 2026-11-26` section.
- **P1-1 (Exact job counts and declared budget):** Independently verified `lefthook.yml` has **27** pre-push leaf jobs (**13 clamped**, **14 unclamped**, exact match with `CONTAINER_UNCLAMPED_JOBS`) and live declared budget **`3330s` (`55.5 min`)** against the **`3450s` (`57.5 min`)** ceiling (`tests/ci/test_lefthook_declared_budget.py:95`). Updated `scripts/ci/lefthook_budget_model.py`, `ADR-104`, and Claims Ledger `C9`.
- **P1-2 (Counterfactual & causal separation):** Added the `Keep pre-push pytest after isolating validate_unused_dependencies` alternative in `Alternatives Considered`, split Fix A (`.venv` poisoning amplifier) from Fix B (structural contention: 81,060 tests, `34.23s` warm / `87.48s` cold whole-tree collection floor across 2,697 files, lockfile invalidations in 2/8 commits, Rule 4 CI duplication), and added 3-run warm `--isolated` timings (`2.26s`, `2.45s`, `2.21s`) plus offline fail-closed behavior to `.project-toolkit/analysis/host-contention-2026-11-26.md` and `ADR-104`.
- **P1-3 (Enforcement-plane boundaries in Trade-offs):** Documented ADR-101 P0/P1/P2 boundaries, `scripts/validation/ruleset_params_baseline.json` parameters (`require_code_owner_review: false`, `required_approving_review_count: 0`, `strict_required_status_checks_policy: false`, admin bypass `actor_id: 5`), head-editable workflow semantics on same-repo `pull_request`, and path-filtered `security` (`Python Security Checks`, `pytest.yml:1109-1113`) and `test-windows-pwsh` jobs outside `test-result` / `REQUIRED_CONTEXTS`.
- **P1-4 (Time-boxed `testmon-seed` review):** Replaced the unmeasurable quarterly trigger with a concrete 30-day calendar review **by 2026-12-26** noting the absence of local on-demand telemetry.
- **P1-5 (Complete Revert Path & docs):** Enumerated all files in `Revert Path` while preserving `--isolated` unconditionally; updated `CONTRIBUTING.md`, `.github/dependency-hygiene/policy.toml:23`, `tests/ci/test_zero_collection_guard_wiring.py`, `tests/ci/test_lefthook_container_bound.py`, and `tests/ci/test_lefthook_declared_budget.py`.
- **P2s (Verified line citations & cleanup guidance):** Updated all `pytest.yml` citations to `:28-37`, `:116-146`, `:318-380`, `:984-1040`, `:1048-1108`, `:1109-1113`, `CODEOWNERS` to `:78`, `test_lefthook_declared_budget.py` to `:95`, noted `python-check` as advisory ruff and `validate_python_syntax` inside `pre-pr-validation`, and documented `uv sync --frozen --extra dev` for cleaning previously contaminated worktrees.

## Round 2

### Agent Positions (Round 2)

| Agent | Vote | Verification Summary |
|-------|------|----------------------|
| architect | Accept | Verified 816-line ADR passes lifecycle cap, top-level amendment and frontmatter align, `pytest.yml` citations exact, `13 clamped / 14 unclamped = 27` and `3330s` live vs `3450s` ceiling exact, time-boxed 2026-12-26 review resolved. |
| critic | Accept | Verified job counts, `CONTRIBUTING.md` updates, file-enumerated Revert Path, `C8`/`C9` claims ledger accuracy, and `test_zero_collection_guard_wiring.py` docstring. One `:97 -> :95` line-reference nit corrected immediately. |
| independent-thinker | Accept | Verified Fix A vs Fix B counterfactual and causal separation, `--isolated` 3-run timings (`2.21s-2.45s`) and offline fail-closed behavior, whole-tree `zero-collection-tests` rationale (`34.23s` warm / `87.48s` cold), and 2026-12-26 calendar review. |
| analyst | Accept | Independently recounted all 27 pre-push leaf jobs (`13 clamped`, `14 unclamped`), recomputed `3330s` live budget vs `3450s` ceiling, and verified every `pytest.yml`, `CODEOWNERS:78`, `policy.toml:23`, and test comment update. |
| security | Accept | Verified ADR-101 P0/P1/P2 boundaries, `ruleset_params_baseline.json` parameters, path-filtered CI job scope, `--isolated` pinning in `checks_ci_parity.py`, and cleanup command. No remaining security findings. |
| high-level-advisor | Accept | Verified all P1/P2 items and marked all four Strategic Review Checklist dimensions `Pass`. |

### Strategic Review Checklist (Final)

| Dimension | Verdict | Evidence |
|-----------|---------|----------|
| Chesterton's Fence | Pass | Historical pre-push pytest rationale preserved; Fix A (`.venv` poisoning) cleanly separated from Fix B (structural contention) with live measurements; CI backstop and ADR-101 limits stated honestly. |
| Path Dependence | Pass | File-enumerated Revert Path preserves `--isolated` unconditionally; parallel headroom files untouched (`git_hook_policy.py`, `host_headroom.py`, `pre_pr_headroom.py`); 2026-12-26 review bounds `testmon-seed` drag. |
| Core vs Context | Pass | Local pre-push test execution/collection is Context duplicating unconditional CI `pytest.yml` (`zero-collection-guard` + 8-leg `pytest-split` -> `Run Python Tests`). |
| Second-System Effect | Pass | Strictly subtractive hook removal plus one `--isolated` flag (`2.21s-2.45s` warm); zero new daemons, schedulers, or local telemetry frameworks. |

## Verdict

- **Decision**: Accepted (6-0 unanimous `Accept` across all 6 review seats).
- **Status**: `ADR-104` Amendment 2026-11-26 is approved for commit and PR merge.
