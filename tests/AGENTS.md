# tests/

Pytest suite: root guard + `tests/conftest.py` + flat `test_*.py` + topic subdirs; consumed by contributors, lefthook, and CI (`pytest.yml` matrix plus four workflows that run named files, see Dependencies), while `cli-smoke.yml` reads nothing here.

## Matters

- Root `conftest.py` autouse `_guard_real_repo_head`: fails (#2316) when a test-launched git command moves real HEAD, fails (#5123) when the test's own call phase also failed, else warns (#3109) (scope: Dangerous assumptions).
- `tests/conftest.py` autouse fixtures: pins `GIT_CONFIG_COUNT=1`+`commit.gpgsign=false`, strips leaked `core.hooksPath`, clears `CI` (branch via `.claude/rules/testing.md` SHOULD-13), defaults `AI_AGENTS_PROJECT_REPO=1`, sanitizes `GIT_*` pointer vars.

## Entry points

- `git_hook_policy.py pytest`: lefthook's pre-push pytest command.
- `AI_AGENTS_PYTEST_FULL_SUITE_LOCALLY=1`: runs the 4 local executing partitions (`_pytest_commands`); CI's matrix is 5 legs (`run_pytest_selected.py`), local bulk covering CI's `bulk` plus `bulk-nested`.
- `check_zero_collection_tests.py`: finds a `test_*.py` under `testpaths` collecting zero tests.
- `packages/ai-agents-cli` `bun test`: the CLI's TS suite, unrelated to repo-root `tests/`.

## Where to look

| Path | Why |
|---|---|
| `conftest.py` (repo root) | Real-repo HEAD guard, git env isolation |
| `tests/conftest.py` | git-config isolation, CI-env clear, `AI_AGENTS_PROJECT_REPO` default, tmp_path sandboxing |
| `pyproject.toml` `[tool.pytest.ini_options]` | `testpaths`, markers, `addopts` |
| `pyproject.toml` `[tool.slow-test-budget]` | per-module second budgets, CI-only |
| `scripts/validation/git_hook_policy.py` | `_resolve_pytest_commands` routes pytest; see Dangerous assumptions |
| `.agents/governance/TESTING-RIGOR.md` | pos+neg+edge evidence obligation |
| `.agents/governance/TESTING-ANTI-PATTERNS.md` | forbidden shapes |
| `.agents/governance/test-location-standards.md` | mirrors `testing.md`, not authoritative alone |
| `tests/mutation/` | `mutation_harness_<issue>.py` pins the incident; `test_mutate_*.py` runs it |

## Skip

- `tests/fixtures/guard_corpus_baseline.json`: pinned finding set, not scratch; `test_guard_diff.py` fails on a lost finding, repair edits the baseline with justification. `tests/ci/fixtures/triage_summary/*.golden`: unreferenced sample output; no tracked file reads them (`git grep -l triage_summary`).

## Constraints

- New skill tests go under `tests/skills/<name>/`; a NEWLY ADDED file colocated under `.claude/skills/`, `src/copilot-cli/skills/`, or `src/claude/skills/` (root reserved in the script, unpopulated) is blocked by `check_colocated_skill_tests.py` (#4838); pre-existing colocated files are grandfathered.
- No duplicate module-level test helper names in one file: `check_duplicate_test_helpers.py` (closes ruff F811's dummy-variable gap).
- No write rooted at `PROJECT_ROOT`/`REPO_ROOT`/`ROOT` outside `tmp_path`/`.pytest_tmp/`: `check_test_tree_writes.py` (#3772).
- No `test_*` function nested inside another (uncollectable, silent): `check_nested_tests.py`; blind spot below.
- A `SKILL.md` documenting a script invocation plus an exit code must be named by a file under `tests/`: `check_skill_contract_tests.py` (pre-PR via `checks_portability.py`, and `validate-vendor-portability.yml`). Deleting such a test reds the gate.
- `tests/evals/rule-scenarios/<rule>.json` and `tests/evals/skill-scenarios/<skill>.json` back the `Rule Activation Coverage` pre-PR gate (`check_rule_activation_coverage.py`, also `validate-rule-activation-coverage.yml`): a missing scenario dir, unparseable scenario JSON, or a scenario naming a deleted rule or skill exits 2; a new rule or skill with no scenario exits 1 against `rule_activation_coverage_baseline.json`.

## Dangerous assumptions

- "`check_nested_tests.py` scans every test file" is false, but not for depth: its `git ls-files` glob matches every depth (bare `*` crosses `/`). Gap: helper modules not named `test_*.py` (`hook_test_helpers.py`, `ci/ratchet_test_helpers.py`) are never opened.
- `checks_coverage.py` looks like a coverage gate; it wraps the advisory `/review`-marker check instead. Real 100% pins: scoped `coverage report --fail-under=100` steps in `pytest.yml`.
- The root HEAD guard looks git-test-only; it is autouse for the whole suite, firing on any real-repo HEAD move in a test's window.
- "My push ran the suite" is false by default: without `AI_AGENTS_PYTEST_FULL_SUITE_LOCALLY=1` a push runs a subset or only collects (imports, asserts nothing).
- `tests/evals/*-scenarios.json` look like inert corpora for the `scripts/eval/` runners; every one is also pytest input. `tests/eval/test_eval_prompt_change.py::TestShippedScenariosValid` loads all of them and requires 2 or more `verdict_options` per scenario, and the critic, qa, orchestrator, and spec files have scenario IDs pinned by `tests/test_completion_terminal_contracts.py`, `tests/test_orchestrator_shared_contracts.py`, and `tests/commands/test_spec_step0_5.py`.

## Dependencies

- Feeds `pytest.yml`'s `zero-collection-guard` (blocking, deliberately no `needs:`/`if:`) and its `test` matrix, which `check-paths` gates from `scripts/test_selection/path_policy.yml` via `dorny/paths-filter`; `select_tests.py` reads the same list locally.
- Six files here are also run by name outside `pytest.yml`: `tests/e2e/test_installed_plugin_hook_e2e.py` (`installed-plugin-hook-guard.yml`), `tests/e2e/test_cli_hook_e2e.py` + `test_plugin_load_smoke.py` (`nightly-cli-smoke.yml`, `-m smoke`), `tests/ci/test_validation_scripts_are_reachable.py` + `test_frontmatter_gate_paths_filter.py` (`validate-generated-agents.yml`, duplicated there on purpose because `check-paths` would skip them on a YAML-only edit); `tests/workflows/test_claude_authorization.py` (`claude.yml`, run as `check_claude_authorization.py --checker`, which exits non-zero when the path is missing). Renaming one reds a workflow the path filter never shows you.
- `lefthook.yml` pre-push expensive stage (`parallel: true`): `python-tests` (15m cap, `AI_AGENTS_PYTEST_WORKER_CAP=4`) and `zero-collection-tests` (4m cap), both unconditional on the path filter (`ci-scripts.md`).
- `packages/ai-agents-cli/tests/*.test.ts` feeds `cli-smoke.yml`'s `verify` job; the only bun/TS suite here.
- `pre_pr.py` gate registry and flags: `scripts/AGENTS.md`.

## Architecture

- `tests/` is flat by default (`git ls-files 'tests/test_*.py' | wc -l`); topic subdirs isolate `tests/ci/`, `tests/hooks/`, `tests/skills/<name>/`, `tests/mutation/`. `--import-mode=importlib` lets same-named modules coexist with and without `__init__.py`.
- `tests/evals/`: ADR-057 prompt-regression corpora plus unit tests of the `scripts/eval/` runners; ADR-058 agent-vs-baseline runners and corpora live in `scripts/eval/` and top-level `evals/` (sibling), not here.
- `tests/skills/github/test_helpers.py` and `tests/workflows/test_claude_authorization.py` carry a `pytest-zero-collection:` marker (import helper; `claude.yml` checker); `check_zero_collection_tests.py` verifies both ways. A module pytest SKIPS at collection needs the other marker, `pytest-zero-collection-conditional: <reason>`, which the gate honors only on a host where the skip actually happened.

## Commands

```bash
uv run pytest tests/ -x
uv run python scripts/validation/git_hook_policy.py pytest
AI_AGENTS_PYTEST_FULL_SUITE_LOCALLY=1 uv run python scripts/validation/git_hook_policy.py pytest
uv run python scripts/validation/pre_pr.py
uv run python scripts/validation/check_zero_collection_tests.py
uv run python scripts/validation/check_nested_tests.py
uv run python scripts/validation/check_colocated_skill_tests.py
cd packages/ai-agents-cli && bun test
```
