# tests/

Pytest suite: root guard, `tests/conftest.py`, flat `test_*.py`, topic subdirs; run by contributors, lefthook, CI.

## Matters

- Root `conftest.py` autouse `_guard_real_repo_head`, every test: fails (#2316) when a test-launched git command moves real HEAD, fails (#5123) when the call phase also failed, else warns (#3109).
- `tests/conftest.py` autouse: git-config isolation (`GIT_CONFIG_COUNT=1`, gpgsign off, no leaked `core.hooksPath`), clears `CI` (`.claude/rules/testing.md` SHOULD-13), defaults `AI_AGENTS_PROJECT_REPO=1`, sanitizes `GIT_*`, caps git discovery at `tmp_path.parent` via `GIT_CEILING_DIRECTORIES`.
- 111 `tests/skills/<name>/test_skill_md_contract.py` via `tests/skills/_template_contract.py`: template render == `src/claude/skills/<name>/SKILL.md` == `.claude/skills/<name>/SKILL.md`, no `@CLAUDE.md` line, no literal `{{`. Hand-editing a shipped SKILL.md reds one.

## Entry points

- `git_hook_policy.py pytest`: lefthook pre-push pytest command.
- `AI_AGENTS_PYTEST_FULL_SUITE_LOCALLY=1`: the 4 local partitions (`_pytest_commands`); CI runs 5 legs (`scripts/ci/run_pytest_selected.py --partition`), local bulk covering CI `bulk` plus `bulk-nested`.
- `check_zero_collection_tests.py`: finds a `test_*.py` under `testpaths` collecting zero tests.

## Where to look

| Path | Why |
|---|---|
| `tests/skills/_template_contract.py` | exempt sets `_NO_COPILOT_MIRROR`, `_LITERAL_BRACE_SKILLS` |

## Skip

- `tests/build_scripts/fixtures/*/expected/`: frozen ADR-109 B1/B2 lossless pins; template render, `src/claude/` and the installed tree must all equal them. No regenerator exists.
- `tests/hooks/fixtures/`: em/en-dash carve-out; `checks_dash.py` skips the prefix for scan and lint targets.

## Constraints

- New skill tests go under `tests/skills/<name>/`. `check_colocated_skill_tests.py` blocks a newly added file colocated under `.claude/skills/`, `src/copilot-cli/skills/` or `src/claude/skills/` (all three populated); pre-existing ones grandfathered.
- `tests/fixtures/guard_corpus_baseline.json` is a pinned finding set; `tests/test_guard_diff.py` fails on a lost finding, repair edits the baseline with a justification.
- No write rooted at `PROJECT_ROOT`/`REPO_ROOT`/`ROOT` outside `tmp_path`/`.pytest_tmp/`: `check_test_tree_writes.py`.
- No `test_*` nested inside another function: `check_nested_tests.py`; blind spot below.
- A `SKILL.md` naming a script invocation plus an exit code needs a test under `tests/`: `check_skill_contract_tests.py`.
- `tests/evals/rule-scenarios/<rule>.json` and `skill-scenarios/<skill>.json` back `check_rule_activation_coverage.py`: unparseable JSON, or a scenario naming a deleted rule or skill, exits 2; an uncovered new rule or skill exits 1 against `rule_activation_coverage_baseline.json`.

## Dangerous assumptions

- `check_nested_tests.py` does not scan every test file, and not by depth: helpers not named `test_*.py` (`tests/hook_test_helpers.py`, `tests/ci/ratchet_test_helpers.py`) are never opened.
- `checks_coverage.py` is not a coverage gate; it wraps the advisory `/review`-marker check. Real 100% pins: `coverage report --fail-under=100` steps in `pytest.yml`.
- "My push ran the suite" is false by default: without `AI_AGENTS_PYTEST_FULL_SUITE_LOCALLY=1` a push runs an import-graph subset or only collects, asserting nothing.
- `tests/evals/*-scenarios.json` are pytest input, not just `scripts/eval/` corpora. `tests/eval/test_eval_prompt_change.py::TestShippedScenariosValid` requires 2+ `verdict_options` each; sibling contract tests pin critic, qa, orchestrator and spec scenario IDs.

## Dependencies

- Feeds `pytest.yml`'s `zero-collection-guard` (blocking, no `needs:`/`if:`) and its 5-leg matrix, gated by `check-paths` from `scripts/test_selection/path_policy.yml`; `select_tests.py` reads it locally.
- Other workflows run named test files (grep below), so a rename reds a check the path filter never shows; `claude.yml` runs `tests/workflows/test_claude_authorization.py` as `scripts/ci/check_claude_authorization.py --checker`.
- `lefthook.yml` pre-push expensive stage: `python-tests` (15m, `AI_AGENTS_PYTEST_WORKER_CAP=4`), `zero-collection-tests` (4m), both ignore the path filter.
- Pre-PR gate registry and flags: `scripts/AGENTS.md`. Template-drift and parity semantics: `build/AGENTS.md`.

## Architecture

- `tests/evals/` is ADR-057 prompt-regression corpora plus tests of its `scripts/eval/` runners; top-level `evals/` is ADR-058 agent-vs-baseline, not pytest input.
- A deliberate zero-collection module carries `pytest-zero-collection:`; `pytest-zero-collection-conditional: <reason>` covers a collection-time skip, honored only where it happened.

## Commands

```bash
uv run pytest tests/ -x
uv run python scripts/validation/git_hook_policy.py pytest
AI_AGENTS_PYTEST_FULL_SUITE_LOCALLY=1 uv run python scripts/validation/git_hook_policy.py pytest
uv run python scripts/validation/pre_pr.py
uv run python scripts/validation/check_zero_collection_tests.py
uv run python scripts/validation/check_nested_tests.py
uv run python scripts/validation/check_colocated_skill_tests.py
grep -rno 'tests/[A-Za-z0-9_/]*\.py' .github/workflows/
cd packages/ai-agents-cli && bun test
```
