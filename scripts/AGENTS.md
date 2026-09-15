# scripts/

Repo automation for developers, lefthook, and CI.

## Matters

- Python only (ADR-042); one legacy exception: `bootstrap-vm.sh`.
- `pre_pr.py`: canonical shift-left gate; `pre_pr_sequence.py`'s `_Gate` row count grows over time (`grep -c "_Gate(" scripts/validation/pre_pr_sequence.py` for the live number).
- `git_hook_policy.py` backs most lefthook jobs via subcommands (`--help` lists them); a minority call other modules directly (e.g. `detect_scope_explosion.py`).

## Entry points

- `uv run python scripts/validation/pre_pr.py` (`--quick`, `--markdown-lint-only`, `--summary-json PATH`).
- `uv run python scripts/validation/git_hook_policy.py <subcommand>` (`--help` lists subcommands).
- `uv run python scripts/check_skill_exists.py --operation {issue,label,milestone,pr,reactions} --action <name>` or `--list-available`.
- `uv run python scripts/new_validated_pr.py` wraps the `github` skill's `new_pr.py`.
- `uv run python scripts/sync_mcp_config.py --sync-all` writes both `.factory/mcp.json` and `.vscode/mcp.json` (`--dry-run` previews instead; `--force` rewrites a destination already in sync).
- `uv run python scripts/detect_scope_explosion.py`: advisory only (ADR-100).

## Where to look

| Path | Why |
|---|---|
| `scripts/validation/pre_pr_sequence.py` | `_SEQUENCE` gate registry (Architecture below) |
| `scripts/validation/git_hook_policy.py` | Most lefthook subcommands; `--help` for the list |
| `scripts/ci/` | Workflow step bodies; `*_count_ratchet.py` pairs with `*_count_baseline.txt` |
| `scripts/eval/` | Runners for `evals/` and eval workflows: `eval-*.py`, `eval_*.py`, plus `software_engineering_library_activation_*.py`; `_*.py` are private modules |

## Skip

- `scripts/ci/*_baseline.txt`: ratchet floors; use each script's `--update`, never hand-edit.
- `scripts/migrations/`: applied, historical; not a pattern to extend.
- `scripts/dev/dogfood_copilot_plugin.py`: single file, outside the gate chain.
- `scripts/bootstrap-vm.sh`: legacy exception; don't model new scripts on it.

## Constraints

- `ci-scripts.md` (auto-loads here) binds MUST-5/7/9/11/12/13/14/18 plus both items numbered `10.` in that file: `Convert every failure signal into a non-zero exit` (`:40`) and `Prove the CLI exits nonzero` (`:61`), the second enforced as an equality ratchet by `scripts/ci/cli_exit_contract_ratchet.py` from `pr-validation.yml`, so a new `scripts/ci/` or `.github/scripts/` script with a `main` needs a test asserting nonzero from `main(argv)` in the same test that calls it.
- `stale_script_refs.py` fails `pre_pr.py` only on command-style references to removed `.ps1`/`.psm1` scripts (`stale_script_refs.py:30-40`); zero tracked PowerShell files remain, so a doc naming a deleted `.py` trips nothing here. No gate catches a removed-Python doc reference. `check_python3_entrypoints.py` (CI only, `pr-validation.yml`) fails a doc telling a reader to run `python3 <script>` when that script imports a third-party package.
- Subprocess text capture MUST use `encoding="utf-8", errors="replace"` (`check_subprocess_encoding.py` enforces it).

## Dangerous assumptions

- `scripts/README.md` opens "PowerShell scripts for the AI Agents system"; stale, every script here is Python (ADR-042).
- `git_hook_policy.py` looks like one script; it backs dozens of unrelated lefthook subcommands. Reading one function does not explain another.
- `scripts/security/run_semgrep.py` looks like the security-scan entry point; it is not: no pre-commit semgrep job exists (pre-commit runs `infrastructure-advisory` and `security-suppressions-staged` instead), and pre-push `security-scan` runs `git_hook_policy.py semgrep-push`, which drives `semgrep` directly.
- `scripts/ci/` and `.github/scripts/` are separate tracked directories, both feeding workflow steps; `ci-scripts.md` binds both. A search that stops at one misses the other.

## Dependencies

- Plugin lib source: `scripts/{github_core,hook_utilities,ai_review_common}`; chain, order, and catchers in `build/AGENTS.md`. `SYNC_FILE_PAIRS` (`sync_plugin_lib.py:41-47`) also carries two single-file copies out of this tree, `hook_utilities/bootstrap.py` and `validation/validate_review_marker.py`, so an unsynced edit to either reds `--check` on a file you did not touch.
- `lefthook.yml` calls `scripts/validation/`, `scripts/maintenance/`, `scripts/testing/` (`-m scripts.testing.mutation_workspace`, the `mutation-safety` singleton guard) and top-level `scripts/*.py`; never `scripts/ci/` or `scripts/eval/`.
- `.github/workflows/*.yml` call `scripts/ci/`, `scripts/validation/`, `scripts/eval/`, `scripts/maintenance/`, `scripts/metrics/`, `scripts/testing/`, `scripts/workflows/`, and read `scripts/test_selection/path_policy.yml` as the paths-filter config (`pytest.yml`). `scripts/metrics/kill_criteria.py` is invoked with a bare `python3` in `drift-detection.yml`, so it is stdlib-only (`ci-scripts.md` MUST-18).
- `scripts/memory/` (`memory_health.py`, `detect_stale.py`, `validate_memory_sizes.py`): documented in `.serena/memories/README.md`; no skill and no hook call them. The memory skills' health and size checks are `.claude/skills/memory/scripts/test_memory_health.py` and `test_memory_size.py` (`git_hook_policy.py memory-size` runs the latter).
- Repo-root `memory_enhancement` symlink -> `scripts/memory_enhancement/`; edit the target, not the symlink.

## Architecture

- `pre_pr_sequence.py` is a data table: `_SEQUENCE` is a tuple of `_Gate` rows (`name`, `run`, `skip_when_quick`, `already_run_by`, `notes`) read by one loop. Adding a gate is a one-line addition. `skip_when_quick` is what `--quick` reads; `already_run_by` names a pre-push fast-stage job, and the loop skips those five rows when `lefthook.yml` sets `AI_AGENTS_PRE_PR_FAST_STAGE_RAN=1`, so a run from a push is not the full sequence.
- `scripts/workflow/` (singular): agent pipeline executor. `scripts/workflows/` (plural): GitHub Actions step helpers, `determine_should_run_from_filters.py` (paths-filter should-run) and `resolve_dispatch_input.py`. Same prefix, unrelated.

## Commands

```bash
uv run python scripts/validation/pre_pr.py
uv run python scripts/validation/git_hook_policy.py <subcommand>
uv run python scripts/ci/ruff_count_ratchet.py --update
uv run python scripts/sync_plugin_lib.py --check
uv run python build/scripts/build_all.py --check
uv run pytest tests/ -x
uv run ruff check .
```
