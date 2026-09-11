# tests/

Pytest suite for the Python codebase (root guards + `tests/conftest.py` + ~400 flat `test_*.py` plus ~25 topic subdirs), and two unrelated bun/TS suites. Consumed by contributors, lefthook, and CI (`pytest.yml`, `cli-smoke.yml`).

## Matters

- Root `conftest.py`'s autouse `_guard_real_repo_head` fixture fails a test that moves the REAL repo's HEAD (attributed via a per-test `GIT_REFLOG_ACTION` token and `GIT_TRACE2`), and warns, or fails if the test's own call phase already failed (issue #5123), on a concurrent external commit in the same worktree. It runs on every test, git-touching or not.
- `tests/conftest.py` autouse fixtures force `GIT_CONFIG_COUNT=1` + `commit.gpgsign=false` (issue #2548), strip a leaked `core.hooksPath` (issue #2996), clear `CI` (issue #4380), default `AI_AGENTS_PROJECT_REPO=1` (issue #2610), and sanitize every `GIT_*` pointer var so `tmp_path` git commands cannot reach the real checkout (issue #4717). The `CI` clear means `os.environ.get("CI")` reads `None` inside any test body even on GitHub Actions; a module-level constant plus `@pytest.mark.skipif` (evaluated at collection, before the fixture runs) is the only way a test can branch on it.
- `git_hook_policy.py pytest` selects an import-graph subset of test files by default, or, when the graph cannot map every changed file, a whole-suite COLLECTION stand-in that imports every test module but never executes an assertion. `AI_AGENTS_PYTEST_FULL_SUITE_LOCALLY=1` is the only way to get the 4 executing partitions: bulk plus `tests/mutation/` under xdist (`-n`, `AI_AGENTS_PYTEST_WORKER_CAP`), then `tests/test_safe_push_pr_branch.py` plus `test_mutation_workspace_signals.py`, then `tests/test_pr_autofix_late_live_state_gate.py` serially (those two mutate process-global state and would corrupt a shared worker pool).
- `checks_coverage.py` in `scripts/validation` is NOT a code-coverage gate despite the name: it wraps the advisory `/review`-marker check. The real 100% pins live only as scoped `coverage report --fail-under=100` steps in `pytest.yml` (e.g. `ai_review_common.verdict`); the 100/80/60 table in root `AGENTS.md` is a PR-body evidence obligation (`TESTING-RIGOR.md`), not an automated repo-wide gate.
- A mutation harness under `tests/mutation/` must report three outcomes (DEAD, SURVIVED, DID-NOT-APPLY), per `.claude/rules/testing.md` MUST 7; a SURVIVED that never applied is not a weak test, it is no test.
- `.agents/governance/test-location-standards.md` is stale: it documents a Pester-only `*.Tests.ps1` layout for a repo with zero PowerShell files. The live rule is `.claude/rules/testing.md`, whose `paths` frontmatter lists all six globs: `tests/**`, `**/*.Tests.ps1`, `**/tests/**`, `.claude/skills/**/tests/**`, `.agents/security/benchmarks/**`, `.claude/rules/testing.md`. The second of those is itself a dead glob: `git ls-files '*.ps1' '*.psm1'` returns zero files.

## Entry points

- `uv run pytest tests/ -x`: direct run, root `AGENTS.md` Standards.
- `uv run python scripts/validation/git_hook_policy.py pytest`: the command lefthook and pre-push run; selects an import-graph subset by default, or a collection-only stand-in when the graph cannot map every changed file.
- `AI_AGENTS_PYTEST_FULL_SUITE_LOCALLY=1 uv run python scripts/validation/git_hook_policy.py pytest`: the only way to run the 4 executing partitions locally instead of the default subset or collection stand-in.
- `uv run python scripts/validation/pre_pr.py`: full 70-gate chain before every push.
- `uv run python scripts/validation/check_zero_collection_tests.py`: find a `test_*.py` under `testpaths` that collects zero tests.
- `cd packages/ai-agents-cli && bun test`: the CLI's OWN TS suite, unrelated to anything under repo-root `tests/`.

## Where to look

| Path | Why |
|---|---|
| `conftest.py` (repo root) | Real-repo HEAD guard, git env isolation, GIT_TRACE2 attribution |
| `tests/conftest.py` | git-config isolation, CI-env clearing, `AI_AGENTS_PROJECT_REPO` default, tmp_path git sandboxing |
| `pyproject.toml` `[tool.pytest.ini_options]` | `testpaths`, markers, `addopts` (`--import-mode=importlib`, `--timeout=120`) |
| `pyproject.toml` `[tool.slow-test-budget]` | per-module second budgets, CI-only enforcement |
| `scripts/test_selection/path_policy.yml` | the one list deciding whether `pytest.yml`'s matrix runs at all |
| `scripts/validation/git_hook_policy.py` (`_resolve_pytest_commands`, `_pytest_commands`, `_full_suite_stand_in`, `~7160-7490`) | selects an import-graph subset, a collection stand-in, or (with `AI_AGENTS_PYTEST_FULL_SUITE_LOCALLY=1`) the 4 executing partitions |
| `.agents/governance/TESTING-RIGOR.md` | pos+neg+edge evidence obligation per changed function |
| `.agents/governance/TESTING-ANTI-PATTERNS.md` | forbidden test shapes (coverage theater, brittle mocks, etc.) |
| `tests/mutation/` | `mutation_harness_<issue>.py` names the incident it pins; the sibling `test_mutate_*.py` files are the runners |
| `tests/hooks/fixtures/` | dash-prohibition carve-out fixtures (`universal.md` MUST-4) |

## Skip

- `tests/__pycache__/` and every nested `__pycache__/`: gitignored bytecode.
- Repo-root `tests/*.test.ts` (2 files): orphaned, nothing runs them; see Dangerous assumptions.
- `.agents/governance/test-location-standards.md`: stale Pester doc, superseded by `testing.md`.
- `tests/fixtures/guard_corpus_baseline.json` is a pinned finding set, not scratch; `tests/test_guard_diff.py` fails when the guard loses a baseline finding, and the documented repair is to edit the baseline and justify it in the commit message. `tests/ci/fixtures/triage_summary/*.golden` are golden-output fixtures, not ratchet baselines.
- `tests/evals/*-scenarios.json`: data fixtures, not tests; consumed by the `tests/evals/test_*.py` runners beside them.

## Constraints

- New tests for a skill go under `tests/skills/<name>/`, never colocated inside `.claude/skills/<name>/tests/` or `src/copilot-cli/skills/<name>/tests/`: `check_colocated_skill_tests.py` blocks a newly added colocated file (issue #4838); those trees ship to customers.
- A `SKILL.md` documenting a script invocation plus an exit code must be named by some file under `tests/`: `check_skill_contract_tests.py`, or the contract can drift silently (issue cited in its docstring: pr-autofix exit codes).
- No duplicate module-level test helper names in one file: `check_duplicate_test_helpers.py` (closes the ruff F811 dummy-variable-regex gap for `_`-prefixed test helpers).
- No write rooted at a `PROJECT_ROOT`/`REPO_ROOT`/`ROOT` binding outside `tmp_path` or `.pytest_tmp/`: `check_test_tree_writes.py`, AST heuristic (issue #3772).
- No `test_*` function nested inside another function (uncollectable, silently): `check_nested_tests.py`; see Dangerous assumptions for its blind spot.
- `tests/hooks/fixtures/` is the ONE place em/en dashes are allowed in the tree: `universal.md` MUST-4 carve-out, honored by the dash-guard hook itself.

## Dangerous assumptions

- "`tests/*.test.ts` runs via `cli-smoke.yml`'s `bun test`" (`docs/project-structure.md:51` says so) is false. `bun test` at `cli-smoke.yml:179` runs with `working-directory: packages/ai-agents-cli`, a sibling tree; the two repo-root `.test.ts` files import repo-root `src/transforms/` and `src/copilot-target-emitter.ts`, and no root `package.json`/`tsconfig.json`/`bunfig.toml` wires either to any runner. Confirmed orphaned in `.agents/audit/2026-09-04-ponytail-audit-over-engineering.md`, finding 9 / Evidence 9.
- "`check_nested_tests.py` scans every test file" is false, but not for depth: its `git ls-files` patterns (`tests/*/test_*.py`, `tests/test_*.py`) match at every depth, because a bare `*` crosses `/`. The real gap is helper modules that do not match `test_*.py`, for example `tests/hook_test_helpers.py`, `tests/ci/ratchet_test_helpers.py`, and `tests/eval/_harness_capability_test_support.py`, among others: the checker never opens them, so a `test_*` function nested inside one is invisible to this gate.
- "`checks_coverage.py` enforces the 100/80/60 coverage table" is false; see Matters.
- "`test-location-standards.md` is the placement authority" is false; it describes a Pester layout the repo no longer has. `testing.md` plus the `check_*` gates above are what actually run.
- "the root HEAD guard only fires on git-heavy tests" is false; it is autouse for the whole suite and fires on ANY real-repo HEAD movement in a test's window, including one from a concurrent human commit in the same worktree.
- "my push ran the suite" is false by default; unless `AI_AGENTS_PYTEST_FULL_SUITE_LOCALLY=1` is set, the default push either runs a narrowed import-graph subset or only collects (imports every module, executes nothing) the whole suite.

## Dependencies

- Feeds `.github/workflows/pytest.yml`'s `zero-collection-guard` (blocking) and `check-paths` job; `scripts/test_selection/path_policy.yml` is read by both that workflow (via `dorny/paths-filter`) and `scripts/test_selection/select_tests.py` locally, so local and CI selection cannot drift apart.
- lefthook.yml pre-push: `python-tests` (`git_hook_policy.py pytest`, 15m cap, `AI_AGENTS_PYTEST_WORKER_CAP=4`) then `zero-collection-tests` (`check_zero_collection_tests.py`, 4m cap), both unconditional on the path filter, per the whole-tree rule in `ci-scripts.md`.
- `mutation-safety` (`scripts.testing.mutation_workspace`) runs as a pre-push singleton ahead of the parallel job group.
- `packages/ai-agents-cli/tests/*.test.ts` feeds `cli-smoke.yml`'s `verify` job (`bun test`, `bun run typecheck`): the ACTIVE bun suite; do not confuse with the orphaned repo-root pair.

## Architecture

- Two unrelated TypeScript test trees share the same `*.test.ts` shape: `packages/ai-agents-cli/tests/` (live, wired to `cli-smoke.yml`) and repo-root `tests/*.test.ts` (2 files, an orphaned TS island per the audit cited above).
- `tests/` is flat by default (398 `test_*.py` directly under `tests/`) with topic subdirs carved out where a concern needs isolation: `tests/ci/` (workflow-script tests), `tests/hooks/` (hook contract tests), `tests/skills/<name>/` (per-skill tests), `tests/mutation/` (mutation harnesses). `--import-mode=importlib` lets same-named modules coexist across dirs that do and do not carry `__init__.py`.
- `tests/evals/` (JSON scenarios + `test_*.py` runners) implements ADR-057/058 regression and agent-vs-baseline checks; top-level `evals/` (outside `tests/`, sibling of `tests/`) holds held-out research corpora and spike write-ups: same first six letters, unrelated content and unrelated consumers.
- Two files, `tests/skills/github/test_helpers.py` and `tests/workflows/test_claude_authorization.py`, carry a `pytest-zero-collection:` marker declaring themselves non-suites (an import helper and a production checker `claude.yml` invokes); `check_zero_collection_tests.py` checks that declaration in both directions.

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
