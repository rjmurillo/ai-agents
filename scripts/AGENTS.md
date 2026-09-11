# scripts/

Repo automation for developers, lefthook, and CI; consumed by contributors running gates locally and by workflow steps that import these modules (ADR-006).

## Matters

- Python only (ADR-042); no new `.sh` files. `bootstrap-vm.sh` is the one legacy exception.
- `pre_pr.py` is the canonical shift-left gate: `pre_pr_sequence.py` registers 70 `_Gate` rows run in order. Run it before every push.
- `git_hook_policy.py` backs every lefthook job through subcommands (`commit-message`, `branch`, `taste`, `stage-generated <kind>`, etc.); `--help` lists them all.
- `scripts/github_core/`, `hook_utilities/`, `ai_review_common/` are the SOURCE for the plugin lib: `sync_plugin_lib.py` copies to `.claude/lib/`, then `build/scripts/build_all.py` mirrors that to `src/copilot-cli/lib/`. Run them in that order; the wrong order exits 0 locally and only `scripts/ci/check_plugin_lib_mirrors.py` catches it in CI.
- Count ratchets (`scripts/ci/*_count_ratchet.py` + `*_baseline.*`) may only fall. A ratchet failure often means your branch is behind `main`, not that you introduced a regression; merge `origin/main` and re-measure before hunting the diff (`ci-scripts.md` item 14).
- New script needs `tests/test_<name>.py` with pos + neg + edge cases and exit-code asserts on `main(argv)`, not just on a helper's return value (`ci-scripts.md` items on silent-failure conversion).

## Entry points

- `uv run python scripts/validation/pre_pr.py` before every push.
- `uv run python scripts/validation/git_hook_policy.py <subcommand>` for any single lefthook job in isolation.
- `uv run python scripts/check_skill_exists.py --operation pr --action <name>` or `--list-available` (operations: `pr`, `issue`, `reactions`, `label`, `milestone`).
- `uv run python scripts/new_validated_pr.py` to open a PR with guardrails enforced (wraps the `new_pr` skill).
- `uv run python scripts/sync_mcp_config.py --sync-all --dry-run --force` to preview or push `.mcp.json` to `.vscode/mcp.json`.
- `uv run python scripts/detect_scope_explosion.py` to check a diff's file count against the scope thresholds.

## Where to look

| Path | Why |
|---|---|
| `scripts/validation/pre_pr_sequence.py` | Ordered gate registry; one `_Gate` row per check, 70 today |
| `scripts/validation/git_hook_policy.py` | Every lefthook subcommand's implementation; `--help` for the full list |
| `scripts/ci/` | Workflow step bodies (ADR-006: no logic in YAML); `*_count_ratchet.py` pairs with `*_baseline.txt` |
| `scripts/eval/` | `eval-*.py` runners called from `evals/` and eval workflows |
| `scripts/testing/mutation_workspace.py` | Backs the `mutation-safety` pre-push singleton guard (`lefthook.yml`) |
| `scripts/security/run_semgrep.py` | Pre-commit and pre-push security scan entry point |
| `scripts/maintenance/gc_worktrees.py`, `repair_packed_refs.py` | Worktree GC and ref repair, run from lefthook and pre-push |
| `scripts/README.md` | Human-facing script index; see Dangerous assumptions below before trusting its framing |

## Skip

- `scripts/__pycache__/` and every nested `__pycache__/`: bytecode cache, not source.
- `scripts/ci/*_baseline.txt`: ratchet floors; read them, never hand-edit (use each script's `--update`).
- `scripts/migrations/`: one-off migrations already applied; historical, not a pattern to extend.
- `scripts/dev/`: `dogfood_copilot_plugin.py`, copies the working tree's Copilot plugin over the installed dogfood copy; single file, not part of the gate chain.
- `scripts/bootstrap-vm.sh`: legacy exception to the Python-only rule; do not model new scripts on it.

## Constraints

- Exit code contract (0 ok / 1 logic / 2 config / 3 external / 4 auth) is enforced per-script; see root `AGENTS.md` Standards for the table (not restated here).
- A doc-interpreter gate plus `scripts/validation/check_python3_entrypoints.py` fails any doc that tells a reader to run `python3 scripts/<name>.py` when that script imports a third-party package (stdlib-only scripts are exempt in principle, but write `uv run python` everywhere regardless).
- `scripts/validation/stale_script_refs.py` fails `pre_pr.py` when a doc names a script that no longer exists in the tree.
- Any script that resolves the repo root and then writes MUST confirm cwd is inside that root before the first write (`ci-scripts.md` MUST-7); `git rev-parse --show-toplevel` reports a claim, not a fact about where you are standing.
- Any claim about what the repo *contains* MUST come from `git ls-tree -r -z HEAD` (or `--name-only` for a path-only inventory), never `git log --all` or a directory walk (`ci-scripts.md` MUST-9).
- Subprocess text capture MUST use `encoding="utf-8", errors="replace"`; `scripts/validation/check_subprocess_encoding.py` enforces it.
- A detected violation MUST exit non-zero and print the examined count alongside the violation count, so "0 violations in N files" is distinguishable from "nothing was examined" (`ci-scripts.md` MUST-11/12).

## Dangerous assumptions

- `scripts/README.md` opens with "PowerShell scripts for the AI Agents system." That is stale: every script here is Python per ADR-042. Do not trust the README's framing over the tree itself.
- `scripts/ci/` and `.github/scripts/` are two separate tracked directories that both feed workflow steps; a search for "the CI script" that stops at one of them misses the other.
- A ratchet reporting a raised count is not proof your change regressed something; check `git rev-parse main` against a fresh fetch first (`ci-scripts.md` item 14) before editing any `*_baseline.*` file.
- `git_hook_policy.py` looks like a single script; it is the implementation for dozens of unrelated lefthook jobs dispatched by subcommand. Reading one function does not tell you how another subcommand behaves.

## Dependencies

- Feeds `.claude/lib/` (via `sync_plugin_lib.py`) and `src/copilot-cli/lib/` (via `build/scripts/build_all.py`); both must be regenerated together, see Matters above.
- `lefthook.yml` calls into `scripts/validation/` and `scripts/maintenance/` for nearly every pre-commit and pre-push job.
- `.github/workflows/*.yml` call into `scripts/ci/`, `scripts/eval/`, `scripts/workflows/`, and `scripts/test_selection/path_policy.yml` (ADR-006: workflows stay thin, logic lives here).
- Memory skills call into `scripts/memory/` (`memory_health.py`, `detect_stale.py`, `validate_memory_sizes.py`).
- The repo-root `memory_enhancement` symlink points at `scripts/memory_enhancement/`; edit the file under `scripts/`, never through the symlink path in a new tool.

## Architecture

- `scripts/validation/pre_pr_sequence.py` is a data table, not control flow: `_SEQUENCE` is a tuple of `_Gate(name, fn)` rows read by one loop in `pre_pr.py`. Adding a gate is a one-line addition to that tuple.
- Plugin lib mirroring is a two-hop chain, not a single copy: `scripts/{github_core,hook_utilities,ai_review_common}/` (source, absolute imports) -> `sync_plugin_lib.py` -> `.claude/lib/` (relative imports) -> `build/scripts/build_all.py` -> `src/copilot-cli/lib/`. Editing the mirrors directly is a no-op; the next regen overwrites them.
- `scripts/workflow/` (singular) is the agent pipeline executor (coordinator, parallel dispatch); `scripts/workflows/` (plural) is unrelated: GitHub Actions dispatch-input resolution. Same prefix, different consumers.

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
