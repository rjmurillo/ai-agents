# Execution Plan: Retire the import-graph test selector and balance pytest legs

## Metadata

| Field | Value |
|-------|-------|
| **Status** | Completed |
| **Created** | 2026-10-08 |
| **Owner** | orchestrator |
| **Complexity** | High |

## Objectives

- [x] M0: Decide the xdist distribution mode and the pytest-split grouping on evidence.
- [x] M1: Move the partition table and the path policy out of the selector.
- [x] M2: Balance the parallel CI legs by recorded duration with pytest-split.
- [x] M3: Pre-push runs collection only.
- [x] M4: Delete the selector, its tests, and its doc references.
- [x] M5: Update ADR-101, ADR-104, and SPEC-6211 with a full-panel debate log.
- [x] M6: Validate locally and in CI, measure, then merge.

## Spec

Issue #6239 is the spec. The evidence is the test-selection sourcing analysis of 2026-10-08.

- Blocked user: every contributor waits on a 478 s median PR run.
- Status quo: the selector narrowed 5 of 30 PR runs and saved about 40 to 60 s when it did.
- Observation: `pytest (bulk-nested-ci)` is the slowest leg in 62 of 80 runs at about 340 s.

## Milestones and tasks

### M0: Evidence (blocks M2, M3, M5)

| Task | Done when | Size |
|---|---|---|
| Worksteal audit: static review plus full suite at `-n 4`, loadfile once, worksteal three times | Verdict SAFE, SAFE-WITH-FIXES, or UNSAFE in the decision log | M |
| pytest-split spike: durations format, xdist support, node IDs under importlib, file grouping, union and missing-test behavior | Answers recorded in the decision log | S |

### M1: Relocate what survives the selector

| Task | Done when | Size |
|---|---|---|
| Move `scripts/test_selection/path_policy.{py,yml}` to `scripts/ci/` | `pytest.yml` `check-paths` filter points at the new path; every importer updated | S |
| Add `scripts/ci/run_pytest_partition.py` with the partition table, full runs only | Unknown partition exits 2; passthrough args kept; no selection import | M |
| One constant for the distribution mode, shared by CI runner and hook | `git_hook_policy.py:655` and the runner read the same value | S |
| Repoint every consumer of the old runner and table | Consumers below pass | M |

Known consumers (grep at build time is the authority):
`tests/ci/test_pytest_xdist_parallelism.py`, `tests/ci/test_pytest_partition_coverage.py`, `tests/ci/test_pytest_paths_filter_roots.py`, `tests/ci/test_pytest_paths_filter_covers_episodes.py`, `tests/workflows/test_pytest_head_guard_windows.py`, `tests/ci/test_ci_scripts_are_wired.py`, `tests/test_check_ai_review_infra_gate.py`, `tests/ci/test_index_line_endings_ci_wiring.py`, `tests/validation/test_closure_manifest_cli.py`, `tests/test_zero_collection_guard_wiring.py`, `tests/test_pytest_non_tmp_policy.py`, `scripts/validation/run_workflow_local_test.py` and its test.

### M2: Duration-balanced legs

| Task | Done when | Size |
|---|---|---|
| Add `pytest-split` to dev dependencies and `uv.lock` | `uv sync --frozen` succeeds | S |
| Generate and commit the durations file; document the refresh command | File committed; size recorded; command in `tests/AGENTS.md` | S |
| Replace `bulk`, `bulk-nested`, `bulk-nested-ci`, `mutation` with N split groups | Each group runs `--splits N --group i` over the same pool | M |
| Keep `safe-push` and `pr-autofix` as dedicated serial legs | Test asserts no split group collects their files | S |
| Keep the unpartitioned files out of the pool | `test_ai_review.py`, `test_verdict.py`, `test_quality_gate.py`, `test_wait_for_unresolved_zero.py` excluded as today | S |
| Add a `primary` matrix key and move every `partition == 'bulk'` step to it | Steps at `pytest.yml:334-380`, `461-491` run exactly once | M |
| Move the merge_group count-ratchet step (`pytest.yml:433`) to a stable leg | Step runs once per merge group | S |
| Update coverage combine, matrix `coverage_file`, `junit_file`, artifact names | `Combine Python coverage` passes; `pytest-results-*` prefix kept | S |
| Slow-test budget sees whole files | Budget runs over merged junit, or groups keep files whole; test proves a budgeted file cannot be diluted | M |
| Union and staleness tests | Union of groups equals the old six-partition collection; a test fails when too many collected IDs lack a duration | M |
| `test-result` aggregator still gates on every leg | `Run Python Tests` fails when any leg fails; checked by test | S |

### M3: Pre-push collection only

| Task | Done when | Size |
|---|---|---|
| Remove the subset path from `scripts/validation/git_hook_policy.py` (`_pytest_commands_for_subset`, selection near lines 7815-7840) | No `select_tests` import; pre-push runs the existing collection stand-in | L |
| Keep the `AI_AGENTS_PYTEST_FULL_SUITE_LOCALLY` opt-in | Opt-in still runs the full suite with no selection | S |
| Update hook tests | `test_pytest_import_selection.py`, `test_collection_probes.py`, `test_collection_contract_surfaces.py`, `test_pushgate_fixes.py`, `test_pre_pr_vendor_portability_real_checker_selection.py`, `test_safe_push_pr_branch.py`, `test_run_pytest_windows.py`, `test_mutation_harness_ciperms.py`, `test_nightly_cli_smoke_security.py` pass or are retired | L |
| Update `lefthook.yml` pre-push comments | Comments match behavior | S |

### M4: Retire the selector

| Task | Done when | Size |
|---|---|---|
| Delete `scripts/test_selection/`, `scripts/ci/run_pytest_selected.py`, `tests/test_selection/`, `tests/ci/test_run_pytest_selected.py` | Files gone | S |
| Remove `PYTEST_SELECT_BASE`, `PYTEST_SELECT_HEAD`, the `mode=` output, and selection comments in `pytest.yml` (lines 16, 111, 265, 389-417) | No dead env vars or stale comments | S |
| Update docs | `.github/AGENTS.md`, `scripts/AGENTS.md`, `tests/AGENTS.md`, `.project-toolkit/context/*/details/*.md`, `gate_latency_classes.py:36` | S |
| Reference gate | `grep -rn "test_selection\|run_pytest_selected"` hits only the allowlist below | S |

Allowlist for the reference gate: `.project-toolkit/plans/`, `.project-toolkit/specs/`, `.project-toolkit/critique/`, `.project-toolkit/analysis/`, `.project-toolkit/retrospective/`, `.serena/memories/`, and ADR history sections.

### M5: ADRs and spec (after M0, M2, M3)

| Task | Done when | Size |
|---|---|---|
| Edit ADR-101 at every selector mention, including the CODEOWNERS requirement | Text matches the new design | M |
| Edit ADR-104 at every selector mention | Pre-push text says collection only | S |
| Amend SPEC-6211 if M0 changes the distribution mode | Spec records the superseding decision | S |
| Full-panel `adr-review` | Debate log committed under `.project-toolkit/critique/` | M |

### M6: Ship

| Task | Done when | Size |
|---|---|---|
| `uv run python scripts/validation/pre_pr.py` | No BLOCKING finding | S |
| Rebuild generated outputs if any template changed | `build_all.py` shows no drift | S |
| Open PR closing #6239 | CI green, threads resolved | M |
| Measure | Slowest `pytest (...)` leg median over the PR's CI runs is under 340 s; Windows job reported separately | S |
| Merge | Merged to main | S |

## Dependency graph

- M0 blocks M2, M3, and M5.
- M1 blocks M2, M3, and M4.
- M2 and M3 run in parallel after M0 and M1.
- M4 follows M2 and M3.
- M5 follows M0, M2, and M3, and finishes before M6.

## Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Deleting the directory breaks `check-paths` | High if missed | High | M1 moves `path_policy` first |
| Test-level split dilutes the slow-test budget | Medium | Medium | M2 budget task |
| Leg names hardcoded elsewhere | High | Medium | Consumer list plus grep gate |
| Durations file goes stale | High | Low | Staleness test, refresh command |
| A split group leaves a test out or doubles it | Low | High | Union test |
| Worksteal breaks file-level isolation | Unknown until M0 | High | M0 decides; loadfile stays if unsafe |
| CI runner and hook disagree on dist mode | Medium | Medium | One shared constant |
| Primary leg exceeds the 10-minute job timeout | Medium | Medium | Make the lightest group primary |
| Windows job becomes the critical path | High | Medium | Out of scope; reported in M6 |
| First renamed runs reset the duration trend baseline | High | Low | Keep `pytest-results-*` prefix; expect one noisy run |

## Decision Log

| Date | Decision | Rationale | Alternatives Considered |
|------|----------|-----------|------------------------|
| 2026-10-08 | Buy, retire the in-house selector | Owner: selection is context, not differentiation | Keep it; replace with testmon |
| 2026-10-08 | No bought selector in CI | testmon missed a subprocess-run script fault | testmon, Smart Tests, Datadog |
| 2026-10-08 | Pre-push runs collection only (D2) | Owner choice; ADR-104 already moves execution to CI | Full suite; testmon opt-in |
| 2026-10-08 | Full-panel ADR review (D3) | The selector is a named CI enforcement component | Reduced panel |
| 2026-10-08 | Re-decide loadfile versus worksteal on evidence (D1) | Owner: do not keep it only because of a past decision | Keep loadfile unexamined |
| 2026-10-08 | Keep the `check-paths` filter; move `path_policy` to `scripts/ci/` | Job-level skip is not test selection | Delete the filter |
| 2026-10-08 | D1 re-decided on evidence: keep `--dist loadfile` | Audit of 43,209 tests: worksteal failed the same 51 pre-existing tests as loadfile in all runs, so isolation is safe; but at CI's `-n 4` median loadfile 392 s against worksteal 438 s (no gain); only `-n 16` showed about 20 percent from one pair. pytest-split already balances legs. | Worksteal everywhere; worksteal only for local large `-n` |
| 2026-10-08 | pytest-split 0.11.0 with `duration_based_chunks` | Spike: works with xdist loadfile and importlib node IDs; union equals full collection with no duplicates; chunks keep collection order, so fewer files split (2 of 6 against 5 of 6) | `least_duration`; a custom file-level bin packer (rejected: building) |
| 2026-10-08 | Slow-test budget runs over merged junit in the coverage job | pytest-split is not file-aware, so a per-leg budget could miss a split file | Per-leg budget |
| 2026-10-08 | Commit `.test_durations` (about 5 MB pretty JSON), refresh by documented command | No repo size lint; pytest-split reads a file at run time; no junit import exists | Restore from an Actions artifact (more moving parts) |

## Progress Log

| Date | Update | Agent |
|------|--------|-------|
| 2026-10-08 | Created plan | orchestrator |
| 2026-10-08 | Revised after critic (REVISE, 15 findings) and pre-mortem | orchestrator |
| 2026-10-08 | Build Phase 1: Tier 3 (clear domain, shared CI and hook infrastructure) | orchestrator |
| 2026-10-08 | Build Phase 2b: trigger activated on `git_hook_policy.py` and `run_workflow_local_test.py`; both LOCAL HIGH; authority record passed | orchestrator |
| 2026-10-08 | M0 to M5 done: audit kept loadfile; pytest-split legs; pre-push collection only; selector deleted; ADR panel reached consensus in 2 rounds (5 Accept, 1 Disagree-and-Commit) | orchestrator |
| 2026-10-08 | Memory gate: selector built for #5050 (878 s per push, path-filter false greens #4345, #4408); partitions keep each job under 10 minutes (#4854); pre-push suites share one timeout (PR #3568); loadfile protects file isolation (SPEC-6211). Each split group must stay under the 10-minute job contract. | orchestrator |
| 2026-10-09 | Merged as 0c801576a in PR #6241, closing #6239 | orchestrator |
| 2026-10-09 | First CI run 37867514214 leg times: split-1 262 s, split-2 300 s, split-3 302 s, split-4 224 s. Slowest leg is under the 340 s target. | orchestrator |
| 2026-10-09 | Windows path-contract job at 317 s is now the critical path (deferred item) | orchestrator |

## Blockers

- None

## Deferred

- Windows path-contract job speed.
- Refactoring the slowest files (`tests/mutation/*`, `tests/ci/test_subprocess_encoding_count_ratchet.py`).
- Automatic refresh of the durations file.
- Larger runners.

## Related

- Issue: #6239
- ADR: ADR-101, ADR-104
- Spec: SPEC-6211
