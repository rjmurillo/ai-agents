# Test Location Standards

This document restates, for `.agents/` readers, rules already enforced by [`.claude/rules/testing.md`](../../.claude/rules/testing.md) (the binding rule; its `paths` frontmatter fires on `tests/**`, `**/*.Tests.ps1`, `**/tests/**`, `.claude/skills/**/tests/**`, `.agents/security/benchmarks/**`) and by the placement gates in [`scripts/validation/`](../../scripts/validation/). Nothing below is new policy; it is documentation catching up to [ADR-042](../architecture/ADR-042-python-migration-strategy.md) (accepted, Python-first migration) and to gates that already ship. Where a claim has no gate behind it, it carries a `Why:` paragraph instead of inventing one.

## PowerShell layout: retired, no tracked survivors

The previous version of this document specified a Pester `*.Tests.ps1` layout under `tests/`. That layout no longer exists. Search performed for this revision, whole-repository scope:

- `git ls-files '*.ps1'` → 0 files.
- `git ls-files '*.Tests.ps1'` → 0 files.
- `git ls-files '*.psd1' '*.psm1'` → one file, [`.PSScriptAnalyzerSettings.psd1`](../../.PSScriptAnalyzerSettings.psd1), linter configuration for CodeQL/PSScriptAnalyzer static analysis (see [`.agents/security/benchmarks/README.md`](../security/benchmarks/README.md)), not a production or test script.
- Every workflow under `.github/workflows/` that has a Pester toggle sets `enable-pester: false` (12 occurrences, `grep -rn enable-pester .github/workflows/`). No workflow invokes `Invoke-Pester`.

Per [`.claude/rules/universal.md`](../../.claude/rules/universal.md) MUST NOT 9, this is an absence claim scoped to the searches above; a PowerShell test file reintroduced later would need its own placement rule, not a revert of this one.

## Directory structure (verified)

```text
ai-agents/
  tests/                          # pytest root (testpaths = ["tests"])
    test_*.py                     # python_files = ["test_*.py"]; most sit here
    ci/, hooks/, skills/<name>/   # topic subdirs
    mutation/                     # mutation harnesses (DEAD/SURVIVED/DID-NOT-APPLY)
    evals/                        # ADR-057 prompt-change scenario JSON + runners
    *.test.ts                     # 2 orphaned bun-shaped files (see TypeScript row below)
  .agents/security/benchmarks/    # second sanctioned test location (security-agent evidence)
  packages/ai-agents-cli/tests/   # live bun/TS suite, unrelated tree
  evals/                          # held-out agent-vs-baseline spikes, NOT pytest input
  .PSScriptAnalyzerSettings.psd1  # linter config, not a script or test
```

Source: `pyproject.toml` `[tool.pytest.ini_options]`. Counts are measurements of a commit, not permanent facts; re-derive with `git ls-files 'tests/**/test_*.py' | wc -l` (629 when this section was written) rather than quoting a number from here.

## Placement rules

| Rule | Statement | Evidence |
|---|---|---|
| 1 | New tests MUST live in `tests/` or `.agents/security/benchmarks/`. No other location is sanctioned. | `.claude/rules/testing.md` MUST 6 |
| 2 | Skill tests MUST live under `tests/skills/<name>/`, never colocated inside `.claude/skills/<name>/tests/` or `src/copilot-cli/skills/<name>/tests/`. Colocated files ship to plugin consumers, who would then execute repo-internal test code. | Issue #4838; gate `check_colocated_skill_tests.py` |
| 3 | Test files MUST be named `test_*.py`. A file named `*_test.py` alone is never collected, because `python_files` lists only the `test_*` prefix. Two tracked files end in `_test.py` and are still collected: both also begin with `test_`, because the module under test is itself named `*_test` (`tests/context-optimizer/test_skill_passive_compliance_test.py`, `tests/validation/test_run_workflow_local_test.py`). That is a suffix inherited from the subject, not a second naming convention. | `pyproject.toml` `[tool.pytest.ini_options]`; `python_files = ["test_*.py"]` |
| 4 | A `test_*.py` that pytest walks MUST collect at least one test, or MUST carry a `pytest-zero-collection:` marker naming why it is a non-suite (an import helper, or a checker another workflow invokes). | Issue #4494; gate `check_zero_collection_tests.py` |
| 5 | A `test_*` function MUST NOT be nested inside another function; pytest never collects it, so a nested test is a silently absent regression guard. Nested test *classes* are collected and are not flagged. | Issue #3879, PR #3688; gate `check_nested_tests.py` |
| 6 | A test file MUST NOT define two module-level helpers of the same name; ruff's F811 dummy-variable regex does not catch this for `_`-prefixed test helpers. | Gate `check_duplicate_test_helpers.py` |
| 7 | A test MUST NOT write under a `PROJECT_ROOT`/`REPO_ROOT`/`ROOT`-rooted path outside `tmp_path` or `.pytest_tmp/`; four confirmed instances left litter that broke `git status` and inflated scanner baselines. | Issue #3772, PR #3688; gate `check_test_tree_writes.py` |
| 8 | A `SKILL.md` that documents a script invocation plus an exit code MUST be named by at least one file under `tests/`, so the documented contract cannot drift silently. | Issue #4249; gate `check_skill_contract_tests.py` |
| 9 | `.claude/rules/testing.md`'s own `.Tests.ps1` glob in its `paths:` frontmatter is a dead glob (zero matching files). It is left in place rather than edited here because narrowing that rule's scope is a `.claude/rules/testing.md` change, out of scope for this governance-doc rewrite. | Why: confirmed via `git ls-files '*.Tests.ps1'` (see above); changing the rule file itself needs its own PR |

## Placement gates: what each rejects, exit codes, where it runs

| Script | Rejects | Exit codes | Wired at |
|---|---|---|---|
| [`check_nested_tests.py`](../../scripts/validation/check_nested_tests.py) | A `test_*` function AST-nested inside another function | 0 none found, 1 nested test found, 2 invalid repo root | pre-push, via `pre_pr.py` gate sequence (`scripts/validation/pre_pr_sequence.py`) |
| [`check_colocated_skill_tests.py`](../../scripts/validation/check_colocated_skill_tests.py) | A newly added `test_*.py`/`*_test.py` under a shipped `.claude/skills/`, `src/copilot-cli/skills/`, or `src/claude/skills/` tree's `tests/` dir | 0 none (or legacy-only), 1 new colocated file found | pre-commit, `--staged-only` |
| [`check_duplicate_test_helpers.py`](../../scripts/validation/check_duplicate_test_helpers.py) | Two module-level test helpers with the same name in one file | 0 none found, 1 duplicate found, 2 invalid repo root | pre-push, via `pre_pr.py` gate sequence |
| [`check_test_tree_writes.py`](../../scripts/validation/check_test_tree_writes.py) | A test file writing outside `tmp_path`/`.pytest_tmp/` via a repo-root-bound path (AST heuristic; false positives possible) | 0 none found, 1 suspect write found, 2 invalid repo root | pre-push, via `pre_pr.py` gate sequence |
| [`check_skill_contract_tests.py`](../../scripts/validation/check_skill_contract_tests.py) | A `SKILL.md` documenting a script + exit code with no test under `tests/` naming it | 0 every in-scope skill bound, 1 unbound skill found, 2 usage/I/O error | CI only, `.github/workflows/validate-vendor-portability.yml` |
| [`check_zero_collection_tests.py`](../../scripts/validation/check_zero_collection_tests.py) | A `test_*.py` under `testpaths` that pytest walks but collects zero tests from (undeclared) | 0 ok, 1 violations found, 2 config error | pre-push (direct `lefthook.yml` job) and CI (`.github/workflows/pytest.yml`) |

All six read the shell-fail-loud contract in [`.claude/rules/ci-scripts.md`](../../.claude/rules/ci-scripts.md) MUST 10-11: a detected violation MUST exit non-zero, never print-and-exit-0. Invoke any of them as `uv run python scripts/validation/<name>.py`.

## Second sanctioned location: security benchmarks

[`.agents/security/benchmarks/`](../security/benchmarks/) holds the security agent's benchmark suite (Issue #756): fixtures under `vulnerable_samples/`, `test_agent_review_quality.py`, `test_cwe22_path_traversal.py`, `test_cwe77_command_injection.py`. `.claude/rules/testing.md`'s `paths:` frontmatter names this tree explicitly, making it the one other placement `.claude/rules/testing.md` MUST 6 permits besides `tests/`.

## One TypeScript test tree

`packages/ai-agents-cli/tests/*.test.ts` (13 files) runs via `bun test` inside
`.github/workflows/cli-smoke.yml`'s `verify` job, `working-directory:
packages/ai-agents-cli`. Place new TypeScript CLI tests there.

A second, orphaned repo-root pair (`tests/command-syntax-translator.test.ts`,
`tests/copilot-target-emitter.test.ts`, importing `src/transforms/` and
`src/copilot-target-emitter.ts`) used to sit beside it: no root
`package.json`/`tsconfig.json`/`bunfig.toml` wired either to any runner.
Confirmed orphaned in
`.agents/audit/2026-09-04-ponytail-audit-over-engineering.md`, finding 9, and
deleted by issue #5456.

## `tests/evals/` vs top-level `evals/`

Same first six letters, unrelated content, unrelated consumers:

- [`tests/evals/`](../../tests/evals/): scenario JSON plus `test_*.py` runners, implementing [ADR-057](../architecture/ADR-057-prompt-behavioral-evaluation.md) prompt-change regression checks ("did this prompt edit help or hurt?"). These ARE pytest input and ARE gated by the placement rules above.
- [`evals/`](../../evals/) (sibling of `tests/`, not inside it): held-out agent-vs-baseline research corpora and spike write-ups ("does this agent's specialization beat a generic baseline?"). Not pytest input; the scenario/spike distinction and the no-fixture-duplication rule are documented in `evals/README.md`.

## pytest configuration (verified against `pyproject.toml`)

| Key | Value |
|---|---|
| `testpaths` | `["tests"]` |
| `python_files` | `["test_*.py"]` |
| `import-mode` | `importlib` (lets same-named modules coexist across dirs with and without `__init__.py`) |
| `timeout` | 120s per test |
| `markers` | `unit`, `integration`, `safe_push_transport` (non-local transport, excluded from pre-push), `security`, `smoke` (real-CLI, nightly only), `windows_path` (Windows-runner only) |

Source: `pyproject.toml` `[tool.pytest.ini_options]`.

## What was dropped from the prior version, and why

- All Pester-specific naming (`{ScriptName}.Tests.ps1`), the `BeforeAll`/`It` examples, and the Pester CI snippet: zero tracked `.ps1` files remain (see PowerShell section above); nothing in this repository executes that pattern today.
- The single-directory "all tests in `/tests/`" rule: superseded by the two-location rule (`tests/` plus `.agents/security/benchmarks/`) that `.claude/rules/testing.md` MUST 6 actually enforces.
- The "no exceptions currently defined" line: false under current gates, which carry documented, evidence-anchored exceptions (`pytest-zero-collection:`-marked non-suites, legacy colocated skill tests that predate the gate).

## Related Documents

- [`.claude/rules/testing.md`](../../.claude/rules/testing.md): binding rule this document expands on.
- [`.claude/rules/ci-scripts.md`](../../.claude/rules/ci-scripts.md): exit-code and fail-loud contract every gate above follows.
- [`.agents/governance/TESTING-RIGOR.md`](TESTING-RIGOR.md): pos+neg+edge evidence bar.
- [`.agents/governance/TESTING-ANTI-PATTERNS.md`](TESTING-ANTI-PATTERNS.md): forbidden test shapes.
- [`.agents/architecture/ADR-042-python-migration-strategy.md`](../architecture/ADR-042-python-migration-strategy.md): the migration this document catches up to.
- [`.agents/architecture/ADR-057-prompt-behavioral-evaluation.md`](../architecture/ADR-057-prompt-behavioral-evaluation.md): scope of `tests/evals/`.
- [`AGENTS.md`](../../AGENTS.md): main project documentation.
