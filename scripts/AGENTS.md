# scripts/

Repo automation. Python only (ADR-042); no new `.sh` (`bootstrap-vm.sh` is legacy).
Exit codes: 0 ok | 1 logic | 2 config | 3 external | 4 auth (ADR-035).
New script -> `tests/test_<name>.py` with pos + neg + edge and exit-code asserts.
Rules firing here: `ci-scripts.md`, `python.md`. Human guide: `scripts/README.md`.

## Map

| Subdir | Role | Called from |
|---|---|---|
| `validation/` | Shift-left gates. `pre_pr.py` runs ~45 named gates (`pre_pr_sequence.py`). `git_hook_policy.py <subcmd>` backs every lefthook job; `--help` lists subcommands. `*_baseline.*` files are ratchets | lefthook, CI |
| `ci/` | Workflow step bodies (ADR-006: no logic in YAML). `*_count_ratchet.py` + `*_baseline.txt` | `.github/workflows/` |
| `workflows/` | `determine_should_run_from_filters.py`, dispatch input resolution | paths-filter jobs |
| `workflow/` | Agent pipeline executor (coordinator, parallel) | orchestrator tooling |
| `github_core/`, `hook_utilities/`, `ai_review_common/` | SOURCE of the plugin lib. `sync_plugin_lib.py` copies to `.claude/lib/`; `build_all.py` then mirrors to `src/copilot-cli/lib/`. Wrong order exits 0 locally; `scripts/ci/check_plugin_lib_mirrors.py` catches it in CI | skills, hooks |
| `memory/`, `memory_enhancement/` (root symlink) | Memory health, tier validation, enhancement layer | memory skills, lefthook |
| `maintenance/` | `gc_worktrees.py`, `repair_packed_refs.py`, worktree reports | pre-commit, pre-push |
| `testing/` | `mutation_workspace` (pre-push check), mutation harness, slow-test budget | lefthook, CI |
| `test_selection/` | `path_policy.yml` decides when `pytest.yml` runs; import-graph selection | CI |
| `eval/` | `eval-*.py` runners (agent-vs-baseline, prompt-change, model sweep, skill overlap) | `evals/`, eval workflows |
| `security/` | `run_semgrep.py`, pre-commit security, security retro | lefthook |
| `quality_gate/`, `pr_maintenance/`, `external_signals/`, `llm_classification/`, `consensus/`, `metrics/`, `traceability/`, `sync/` | Extracted workflow logic (quality gate, AI review, PR maintenance, spec drift, consensus voting) | workflows |
| `modules/`, `utils/`, `progress/`, `test_result_helpers/`, `mcp_cli/`, `dev/`, `migrations/` | Shared helpers, MCPorter wrapper, dogfood plugin, one-off migrations | |

Root scripts worth knowing: `sync_mcp_config.py` (`.mcp.json` -> `.vscode/mcp.json`; `--sync-all --dry-run --force`),
`check_skill_exists.py --operation pr --action <name>` or `--list-available`,
`validate_session_json.py <log> [--pre-commit]` (validate-if-present; creation discontinued),
`new_validated_pr.py`, `validate_workflows.py [files]`, `detect_scope_explosion.py` (warn 10, strong 20, block 50 files),
`redact_secrets.py`, `update_memory_index_tokens.py --check`.

## Traps

- `stale_script_refs.py` gate: a doc naming a removed script fails `pre_pr.py`.
- Doc-interpreter gate plus `check_python3_entrypoints.py` (CI): bare `python3 x.py` for a script importing third-party fails; write `uv run python`.
- Ratchets are single integers; a count below baseline passes (concurrent-merge race, #4057). `--update` records a new floor.
- Verify cwd is inside `git rev-parse --show-toplevel` before the first write (ci-scripts MUST-7).
- Repo-content claims come from `git ls-tree -r -z HEAD`, never `git log --all` or a directory walk (MUST-9).
- Subprocess text capture: `encoding="utf-8", errors="replace"` (`check_subprocess_encoding.py`).
- A detected violation must exit non-zero; print examined count next to violation count (MUST-11, MUST-12).
