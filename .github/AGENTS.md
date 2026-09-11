# .github/

CI and Copilot integration. Logic lives in `scripts/ci/` and `.github/scripts/`; workflow YAML
only wires steps (ADR-006; `scripts/ci/adr006_run_block_scanner.py --max 0` in `pr-validation.yml`).
Actions are SHA-pinned (`staged-action-pins` hook, `check_ci_dependency_pins.py`).
Rules firing here: `ci-scripts.md`, `security.md`, `generated-artifacts.md`, `token-economy.md`.
Before touching agents, prompts, instructions, or hooks shared with Copilot CLI: `agent-harness-reference`.

| Path | Status |
|---|---|
| `workflows/*.yml` (60) | Hand-edited. `scripts/validate_workflows.py`; run changed workflows locally pre-push (`git_hook_policy.py workflow-local`) |
| `agents/*.agent.md` | HAND copy; parity group with `templates/agents/`, `src/claude/`, `.claude/agents/` |
| `instructions/*.instructions.md` | GENERATED from `.claude/rules/` (`applyTo` frontmatter only) |
| `prompts/pr-quality-gate-*.md` | GENERATED from `.claude/skills/review/references/` |
| `prompts/*.md` (other) | Hand prompts for workflows (spec checks, triage, drift issue, synthesis) |
| `copilot-instructions.md` | Copilot always-on entry; byte ratchet in `scripts/validate_workspace_budget.py` |
| `scripts/*.py` | Workflow helpers; tests in `tests/` |
| `actions/` | Composites: `ai-review`, `setup-code-env`, `test-installed-plugin-hooks`, `validate-plugin-manifests`, `workflow-debounce` |
| `plugin/marketplace.json`, `copilot/settings.json`, `codeql/` | Copilot marketplace, Copilot settings, CodeQL config (`python`, `actions`) |
| `PULL_REQUEST_TEMPLATE.md`, `CODEOWNERS`, `labeler.yml`, `bot-authors.yml` | PR body layout (validated by `pr-validation.yml`), ownership, labels, bot identities |

## Workflows to know

| Workflow | Trigger | Backs |
|---|---|---|
| `pr-validation.yml` | PR | PR body standards, commit count, ADR-006 scan, rule `paths:` keys, `check_python3_entrypoints.py`, memory-index token ratchet |
| `pytest.yml` | PR, push; gated by `scripts/test_selection/path_policy.yml` | `uv run pytest` |
| `validate-generated-agents.yml` | PR (internal paths-filter) | `build/generate_agents.py --validate` |
| `drift-detection.yml` | Mon 09:00 UTC, manual | `detect_agent_drift.py` -> alert issue via `scripts/ci/drift_*.py` |
| `validate-plugin-version-bump.yml` | `.claude/**`, `src/claude/**`, `src/copilot-cli/**` | No `version` in plugin manifests (ADR-092) |
| `validate-plugin-manifests.yml`, `installed-plugin-hook-guard.yml`, `hook-contract-check.yml` | Plugin and hook changes | Manifest schema, installed-hook runtime contract |
| `cli-smoke.yml`, `nightly-cli-smoke.yml` | CLI and plugin changes, nightly | Install smoke, `bun test` for `tests/*.test.ts` |
| `passive-context-budget.yml`, `instruction-budget.yml` | Doc changes | 2000-token cap on root `AGENTS.md`, `CLAUDE.md`; mirror byte budgets |
| `codeql-analysis.yml`, `dependency-review.yml`, `test-codeql-integration.yml` | PR, push, weekly | Security scanning |
| `claude.yml`, `rjmurillo-bot.yml`, `pr-maintenance.yml`, `post-pr-retrospective.yml`, `auto-assign-reviewer.yml`, `label-pr.yml` | Events, schedules | Bot automation |
| `validate-*.yml` (paths, planning artifacts, ADR numbers, spec IDs, rule activation coverage, vendor portability, artifact retention) | Path-filtered PRs | Corpus gates |

## Conventions

- New AI workflow with concurrency: add to `.github/scripts/measure_workflow_coalescing.py` `DEFAULT_WORKFLOWS`; group `{prefix}-${{ github.event.pull_request.number || inputs.pr_number }}` with `cancel-in-progress: true`. Coalescing is best-effort: 5-10% duplicate runs is normal, over 20% is a bug (ADR-026, #803).
- No merge queue (user-owned repo). Count ratchets accept count below baseline so concurrent cleanup PRs never red `main` (#4057, #4214).
- Path filtering via `dorny/paths-filter` plus `scripts/workflows/determine_should_run_from_filters.py`; required checks still emit a skip job.
- Minimal permissions per job; bot actors excluded; `gh` calls pass `--repo "$GITHUB_REPOSITORY"`.
- A new gate PR must quote the gate passing against the full corpus before merge (ci-scripts MUST-13).
