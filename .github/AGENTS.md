# .github/

CI workflows plus generated Copilot mirrors, agents, prompts, and hook JSON for this repo.

## Matters

- Generated, never hand-edit: `instructions/`, `agents/*.agent.md`, `hooks/`, all in `build/scripts/build_all.py`'s `OWNED_PREFIXES`. `prompts/pr-quality-gate-*.md` regenerates only with `build/scripts/generate_pr_quality_prompts.py`, which `build_all.py` does not run.
- `copilot-instructions.md`: Copilot's always-on entry point (every Copilot CLI session). Byte ratchet 6351 (4707 today) in `scripts/validate_workspace_budget.py`, enforced by `tests/test_workspace_limits.py::test_per_file_limit` inside the required `Run Python Tests`; `scripts/test_selection/path_policy.yml`'s `**/*.md` puts every edit here into that matrix.
- Cross-harness work: read `agent-harness-reference` first, route it through `ai-agents-portability-campaign`.

## Entry points

- `workflows/pr-validation.yml`, job `Validate PR`: required check. PR body shape, workflow YAML, ADR-006 scan, rule `paths:` keys, bare-`python3` doc entrypoints, memory-index token ratchet.
- `.github/scripts/*.py` (18) and repo-root `scripts/ci/` (105) carry most job logic; others scatter, mostly `scripts/validation/`. Grep it. There is no `.github/scripts/ci/`.

## Where to look

| Path | Why |
|---|---|
| `workflows/*.yml` (56) | Hand-edited; schema and SHA pins by `validate_workflows.py` |
| `agents/*.agent.md` (31) | Generated; do not hand-edit |
| `agents/security/references/*.md` | Hand copy of `src/claude/security/references/`; edit both |
| `instructions/*.instructions.md` | `generate_rules.py` from `src/claude/rules/` |
| `hooks/` | Binplaced from `src/copilot-cli/hooks/`; `hooks.json` registers nothing |
| `prompts/` (33) | 12 `pr-quality-gate-*.md` generated; 7 `pr-quality.*.prompt.md` hand-written, dot not hyphen |
| `agents/pr-comment-responder.prompt.md` | Only `.prompt.md` under `agents/`; hand-maintained |

## Skip

- `ISSUE_TEMPLATE/`: unread. `FUNDING.yml`: read only by `labeler.yml`. `CLAUDE.md`: claude-mem stub importing this file.

## Constraints

- Job bodies live in `scripts/ci/` or `.github/scripts/`, tested in `tests/`.
- SHA pins: `scripts/validation/git_hook_policy.py staged-action-pins` locally, `scripts/validate_workflows.py` in `pr-validation.yml`.
- New concurrency groups register in `.github/scripts/measure_workflow_coalescing.py`'s `DEFAULT_WORKFLOWS` with `cancel-in-progress: true` (ADR-026).
- `gh` calls in `.github/scripts/*.py` build the path as `repos/{owner}/{repo}/...`; `--repo`/`--repository` default empty and fall back to the git remote.

## Dangerous assumptions

- "`instructions/` mirrors `.claude/rules/`": since ADR-109 B2 the generator source is `src/claude/rules/`; the canonical edit is `templates/rules/<name>.md`.
- "`binplace.yaml` has a `prompts` row, so `build_all.py` writes `prompts/`": that row's `plugin_tree` is null, so binplace skips it.
- "`instruction-budget.yml` caps root `AGENTS.md`/`CLAUDE.md`": it gates the always-on rule corpus. Root doc cap is `passive-context-budget.yml`.
- Green `validate-generated-agents.yml` or `agent-drift-detection.yml` on a PR touching no agent file proves nothing: both skip behind a paths filter, and the latter on `[skip-drift-check]` in any commit message.

## Dependencies

- Agent render map: `templates/AGENTS.md`. Generator order, `OWNED_PREFIXES`, binplace, drift and parity semantics: `build/AGENTS.md`; `build_all.py --check` in `Validate Generated Files` is the stale-tree gate.
- `adr006_run_block_scanner.py` and `check_python3_entrypoints.py` run in neither `pre_pr.py` nor lefthook; a green `pre_pr.py` does not predict `Validate PR`.
- `instructions/` and `copilot-instructions.md` reach Copilot only; Claude Code reads `.claude/rules/`. Cloud Copilot loads only default-branch `hooks/*.json`.

## Architecture

- `generate_rules.py` writes both mirrors in one run, renaming `paths:` to `applyTo:` and dropping `priority:`/`alwaysApply:`: `instructions/` keeps every rule (28), `src/copilot-cli/instructions/` drops rules whose globs are all internal-only (22, issue #4317). Counts are not meant to match.
- `prompts/pr-quality-gate-*.md`: one-way edge from `.claude/skills/review/references/`, outside `build_all.py --check`. Stale output blocks at lefthook `review-axis-drift` and the `Review-axes drift check` step.

## Commands

```bash
uv run python scripts/ci/adr006_run_block_scanner.py --max 0
uv run python scripts/validate_workflows.py
uv run python build/scripts/generate_rules.py
uv run python build/scripts/generate_pr_quality_prompts.py --dry-run
uv run python build/scripts/build_all.py --check
uv run python scripts/validate_workspace_budget.py
uv run python -m scripts.validation.passive_context_budget --ci
uv run python -m scripts.validation.instruction_budget --ci
uv run python scripts/validation/pre_pr.py
```
