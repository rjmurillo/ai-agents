# scripts/

Repo automation for developers, lefthook, and CI.

## Matters

- Python only (ADR-042); sole exception `scripts/bootstrap-vm.sh`, not a model for new scripts.
- `pre_pr.py` runs the gates in `pre_pr_sequence.py` (`grep -c "_Gate(" scripts/validation/pre_pr_sequence.py` for the count).
- `git_hook_policy.py` is one file behind dozens of unrelated lefthook subcommands; 34 of 76 jobs call other modules directly. Reading one handler explains no other.

## Entry points

- `uv run python scripts/validation/pre_pr.py` (`--quick`, `--markdown-lint-only`, `--summary-json PATH`).
- `uv run python scripts/validation/git_hook_policy.py <subcommand>` (argparse subparsers; `--help` lists them).
- `uv run python scripts/check_skill_exists.py --operation <op> --action <name>`, or `--list-available`.
- `uv run python scripts/new_validated_pr.py` wraps the `github` skill's `new_pr.py`.
- `uv run python scripts/sync_mcp_config.py --sync-all` writes `.factory/mcp.json` and `.vscode/mcp.json` (`--dry-run`, `--force`).

## Where to look

| Path | Why |
|---|---|
| `scripts/eval/` | Runners for `evals/`; `_*.py` are private modules |

## Skip

- `scripts/ci/*_baseline.txt`: ratchet ceilings, paired with `*_ratchet.py`; use `--update`, never hand-edit.
- `scripts/migrations/`: applied; not a pattern to extend.

## Constraints

- Subprocess text capture MUST pass `encoding="utf-8", errors="replace"` (`check_subprocess_encoding.py`).

## Dangerous assumptions

- `scripts/README.md` opens "PowerShell scripts for the AI Agents system": stale, zero tracked `.ps1`/`.psm1` remain.
- `stale_script_refs.py` matches only `.ps1`/`.psm1` (none tracked, so it reports nothing); a doc naming a deleted `.py` trips no lefthook or CI gate, only `orphan-ref-validator` (`/build` exit gate 4).
- `scripts/security/run_semgrep.py` runs only from `git_hook_policy.py semgrep`, which lefthook never calls; pre-push `security-scan` uses `semgrep-push` and its inline `_run_semgrep_tree`.
- `scripts/ci/` and `.github/scripts/` are separate trees, both feeding workflow steps; `ci-scripts.md` binds both.

## Dependencies

- Plugin lib source: `scripts/{github_core,hook_utilities,ai_review_common}`, `hook_utilities/bootstrap.py`, `validation/validate_review_marker.py`; `build_all.py` (`build/scripts/lib_mirror.py`) renders them into both plugin lib trees and binplaces the claude side (ADR-109 B5). `sync_plugin_lib.py` is a deprecated shim; add no caller.
- `lefthook.yml` calls `scripts/validation/`, `scripts/maintenance/`, `-m scripts.testing.mutation_workspace`, and top-level `scripts/*.py`; never `scripts/ci/` or `scripts/eval/`.
- `.github/workflows/*.yml` call `scripts/ci/`, `scripts/validation/`, `scripts/workflows/`, `scripts/eval/`, `scripts/metrics/`, `scripts/maintenance/`, `scripts/testing/`; `pytest.yml` reads `scripts/test_selection/path_policy.yml` as its paths filter.
- `scripts/metrics/kill_criteria.py` is invoked by a bare interpreter in `drift-detection.yml`: stdlib only.
- `scripts/memory/`: documented in `.serena/memories/README.md`; no skill and no hook call it (only `tests/`). Live checks: `.claude/skills/memory/scripts/test_memory_health.py`, `test_memory_size.py` (`git_hook_policy.py memory-size`).
- Repo-root `memory_enhancement` symlink -> `scripts/memory_enhancement/`; edit the target.

## Architecture

- `_SEQUENCE`: a tuple of `_Gate(name, run, skip_when_quick, already_run_by, notes)` read by one loop, so adding a gate is one line. `--quick` skips `skip_when_quick` rows; `AI_AGENTS_PRE_PR_FAST_STAGE_RAN=1` from `lefthook.yml` skips the five `already_run_by` rows, so a push run is not the full sequence.
- `scripts/workflow/` (singular): agent pipeline executor. `scripts/workflows/` (plural): Actions step helpers. Unrelated.

## Commands

```bash
uv run python scripts/validation/pre_pr.py
uv run python scripts/validation/git_hook_policy.py <subcommand>
uv run python build/scripts/build_all.py --check
```
