# tests/

Pytest suite: root guard, `tests/conftest.py`, flat `test_*.py`, topic subdirs; run on demand locally and by CI.

## Matters

- Root `conftest.py` autouse `_guard_real_repo_head`: fails (#2316) if a test git command moves real HEAD, fails (#5123) when call phase also failed, else warns (#3109).
- `tests/conftest.py` autouse: git-config isolation (`GIT_CONFIG_COUNT=1`, gpgsign off, no leaked `core.hooksPath`), clears `CI` (`rule-testing.md` SHOULD-13), defaults `AI_AGENTS_PROJECT_REPO=1`, sanitizes `GIT_*`, caps git discovery at `tmp_path.parent` (`GIT_CEILING_DIRECTORIES`).
- 111 `tests/skills/<name>/test_skill_md_contract.py` (`tests/skills/_template_contract.py`): template == `src/claude/skills/<name>/SKILL.md` == `.claude/skills/<name>/SKILL.md`, no `@CLAUDE.md`, no literal `{{`.

## Entry points

- `git_hook_policy.py pytest`: on-demand local `pytest --testmon` wrapper (not in pre-push per ADR-104 2026-11-26).
- `AI_AGENTS_PYTEST_FULL_SUITE_LOCALLY=1`: 4 local partitions, no testmon; CI runs 8 legs (`split-1`..`6`, `safe-push`, `pr-autofix`).
- `check_zero_collection_tests.py`: catches zero-collecting `test_*.py` (CI `zero-collection-guard` runs unconditionally).
- One leg: `uv run python scripts/ci/run_pytest_partition.py --partition split-1`. Timings from Actions cache `pytest-split-durations-` (saved on main pushes; fallback splits by count). `duration_gate_check.py` fails main on repeat leg >480s; PRs and 1.5x spread warn.

## Where to look

| Path | Why |
|---|---|
| `tests/skills/_template_contract.py` | exempt sets `_NO_COPILOT_MIRROR`, `_LITERAL_BRACE_SKILLS` |

## Skip

- `tests/build_scripts/fixtures/*/expected/`: frozen ADR-109 B1/B2 lossless pins; template, `src/claude/`, and installed tree must match. No regenerator.
- `tests/hooks/fixtures/`: em/en-dash carve-out (`checks_dash.py` skips prefix).

## Constraints

- New skill tests go under `tests/skills/<name>/` (`check_colocated_skill_tests.py` blocks colocated tests under `.claude/skills/`, `src/copilot-cli/skills/`, `src/claude/skills/`).
- `tests/fixtures/guard_corpus_baseline.json`: pinned finding set; `tests/test_guard_diff.py` fails on lost findings.
- No write under `PROJECT_ROOT`/`REPO_ROOT`/`ROOT` outside `tmp_path`/`.pytest_tmp/`: `check_test_tree_writes.py`.
- No nested `test_*` inside functions: `check_nested_tests.py` (blind spot below).
- A `SKILL.md` naming a script + exit code needs a test under `tests/`: `check_skill_contract_tests.py`.
- `tests/evals/rule-scenarios/<rule>.json` and `skill-scenarios/<skill>.json` back `check_rule_activation_coverage.py` (exit 2 on bad JSON/deleted item; exit 1 on uncovered new rule/skill vs `rule_activation_coverage_baseline.json`).

## Dangerous assumptions

- `check_nested_tests.py` ignores helpers not named `test_*.py` (`tests/hook_test_helpers.py`, `tests/ci/ratchet_test_helpers.py`).
- `checks_coverage.py` wraps advisory `/review`-marker check, not coverage. Real 100% pins: `coverage report --fail-under=100` in `pytest.yml`.
- "My push ran the suite" is false: pre-push does not run pytest (ADR-104 2026-11-26). Run targeted `uv run pytest <paths>` locally; CI runs all legs.
- `tests/evals/*-scenarios.json` are pytest input (`test_eval_prompt_change.py::TestShippedScenariosValid` requires 2+ `verdict_options`; sibling tests pin critic/qa/orchestrator/spec IDs).

## Dependencies

- Feeds `pytest.yml` `zero-collection-guard` (blocking, no `needs:`/`if:`) and 8-leg matrix (never `check-paths`-gated).
- Other workflows run named test files (grep below); `claude.yml` runs `tests/workflows/test_claude_authorization.py` via `check_claude_authorization.py --checker`.
- `lefthook.yml` pre-push omits `python-tests` and `zero-collection-tests` (ADR-104 2026-11-26); CI `pytest.yml` is the gate.
- Pre-PR gate registry: `scripts/AGENTS.md`. Template drift/parity: `build/AGENTS.md`.

## Architecture

- `tests/evals/`: ADR-057 corpora & `scripts/eval/` tests. `evals/`: ADR-058 agent-vs-baseline (not pytest); `evals/skill-rewrites/`: ADR-127 evidence.
- Deliberate zero-collection modules carry `pytest-zero-collection:`; `pytest-zero-collection-conditional: <reason>` covers collection-time skips.

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
