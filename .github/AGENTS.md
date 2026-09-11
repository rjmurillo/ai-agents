# .github/

CI workflows, generated Copilot-CLI mirrors, and hand-maintained agent parity copies; consumed by GitHub Actions and by GitHub Copilot CLI when it runs inside this repo.

## Matters

- ADR-006: workflow YAML has no branching logic. Every job calls a module under `scripts/ci/` or `.github/scripts/`, tested under `tests/`.
- Two surfaces here are generated and must never be hand-edited: `instructions/*.instructions.md` (from `.claude/rules/`, via `build/scripts/generate_rules.py`) and `prompts/pr-quality-gate-*.md` (from `.claude/skills/review/references/`, via `build/scripts/generate_pr_quality_prompts.py`).
- `agents/*.agent.md` is the opposite: hand-maintained, not generated. It must move in lockstep with `.claude/agents/*.md` (`build/scripts/validate_install_parity.py` blocks a solo diff) and is checked for semantic drift weekly (`build/scripts/detect_agent_drift.py`).
- `copilot-instructions.md` is Copilot's always-on entry point for this repo; it carries its own byte ratchet (6351 bytes, `scripts/validate_workspace_budget.py`), separate from the 2000-token cap on root `AGENTS.md`/`CLAUDE.md`.
- Before touching an agent, prompt, instruction, or hook file shared with Copilot CLI, read the `agent-harness-reference` skill first and route the change through `ai-agents-portability-campaign`.
- No merge queue on this repo. Count ratchets under `scripts/ci/` accept a count at or below their own baseline, so two concurrent cleanup PRs never both red `main` on the same violation.

## Entry points

- `workflows/pr-validation.yml`: the required check every PR runs (PR body shape, commit count, ADR-006 scan, rule `paths:` keys, bare-`python3` doc entrypoints, memory-index token ratchet).
- `copilot-instructions.md`: loaded into every Copilot CLI session in this repo.
- `PULL_REQUEST_TEMPLATE.md`: the body shape `pr-validation.yml` checks every PR against.
- `scripts/ci/*.py` and `scripts/*.py`: the logic behind every workflow above.

## Where to look

| Path | Why |
|---|---|
| `workflows/*.yml` (58 tracked, plus 2 `.yml.disabled`) | Hand-edited; schema-checked by `scripts/validate_workflows.py` inside `pr-validation.yml` |
| `agents/*.agent.md` (31) + `agents/security/references/*.md` | Hand copy, parity group with `templates/agents/*.shared.md`, `src/claude/`, `.claude/agents/`; the `references/` subdir backs `security.agent.md` only |
| `instructions/*.instructions.md` (29) | Generated mirror of `.claude/rules/*.md`; `paths:` becomes `applyTo:` |
| `prompts/pr-quality-gate-*.md` | Generated from `.claude/skills/review/references/*.md`; owned in `CODEOWNERS` |
| `prompts/*.md` (other) | Hand prompts for workflow steps (spec checks, triage, drift issue, synthesis) |
| `copilot-instructions.md`, `copilot-code-review.md` | Copilot always-on entry (see Matters); review-comment volume/confidence rules for AI reviewers (issue #326) |
| `scripts/*.py` (19, plus `ci/`) | Workflow helper modules; tests live at repo-root `tests/`, not `.github/tests/` |
| `actions/` | Composites: `ai-review`, `setup-code-env`, `test-installed-plugin-hooks`, `validate-plugin-manifests`, `workflow-debounce` |
| `plugin/marketplace.json`, `copilot/settings.json`, `codeql/*.yml` | Copilot marketplace entry (`src/copilot-cli` source, no `version` per ADR-092), Copilot CLI settings, CodeQL config/suppressions |
| `CODEOWNERS`, `labeler.yml`, `bot-authors.yml` | Owner review gates, path-based PR labels, bot-actor identification |

## Skip

- `workflows/*.yml.disabled` (`droid-review.yml.disabled`, `droid.yml.disabled`): tracked but inert, GitHub never runs a `.disabled` workflow file.
- `scripts/__pycache__/`, `actions/workflow-debounce/__pycache__/`: untracked bytecode, ignore if seen on disk.
- `ISSUE_TEMPLATE/`, `FUNDING.yml`: boilerplate, no gate reads them.

## Constraints

- Actions pin to a commit SHA, never a floating tag: enforced locally by `git_hook_policy.py staged-action-pins` and remotely by `scripts/validate_workflows.py` inside the required `pr-validation.yml` (`security.md` MUST-4).
- A workflow whose gate reads the *whole tree*, not just the diff, must run unconditionally on `push` to `main`; a path filter there manufactures a false-green skip job (`ci-scripts.md`). `instruction-budget.yml` has no path filter for this reason.
- A step invoked with bare `python3` (no preceding `uv`/`astral-sh/setup-uv` step) may only import the standard library; a third-party import fails before the script runs, with no local reproduction (`ci-scripts.md` MUST-18). Several `ai-spec-validation.yml` steps are in this shape.
- A new gate PR must quote the gate passing against the full corpus before merge, not just a fixture test (`ci-scripts.md` MUST-13).
- New workflow concurrency groups register in `.github/scripts/measure_workflow_coalescing.py`'s `DEFAULT_WORKFLOWS` and use `cancel-in-progress: true`; coalescing is best-effort (over 20% duplicate runs is a bug, ADR-026, issue #803).
- `gh` calls from `.github/scripts/*.py` pass `--repo`/`--repository` explicitly.

## Dangerous assumptions

- "SHA pinning is enforced by `check_ci_dependency_pins.py`": wrong, that script checks hand-written `pkg==version` pins against `pyproject.toml`. The Action-SHA gate is `staged-action-pins` locally and `scripts/validate_workflows.py` in CI.
- "`instruction-budget.yml` caps root `AGENTS.md`/`CLAUDE.md`": wrong, it gates the always-on rule corpus per language. The 2000-token cap on root docs (4000 on `.claude/CLAUDE.md`) is `passive-context-budget.yml`, a different workflow.
- "`.github/agents/*.agent.md` is generated like `src/copilot-cli/agents/`": wrong, only `src/copilot-cli/agents` and `src/vs-code-agents` are generated (`build/generate_agents.py --validate`). `.github/agents/` is hand-copied and only parity-checked.
- A green `validate-generated-agents.yml` or `drift-detection.yml` run on a PR that touched no agent files is not proof the trees still match; both use internal path filters or a weekly cron, not a full-corpus run on every push.

## Dependencies

- Feeds `build/generate_rules.py` (-> `instructions/`) and `build/generate_pr_quality_prompts.py` (-> `prompts/pr-quality-gate-*.md`); both regenerate and commit in the same change as their source.
- `agents/*.agent.md` feeds `build/scripts/validate_install_parity.py` (structural) and `build/scripts/detect_agent_drift.py` (semantic, wired into `workflows/drift-detection.yml`).
- `pr-validation.yml` mirrors `scripts/validation/pre_pr.py`'s constituent checks; several of its steps are also lefthook pre-push jobs.
- `copilot-instructions.md` and `instructions/*.instructions.md` are what Copilot CLI loads; a change here has no effect on Claude Code, which reads `.claude/rules/*.md` directly.

## Architecture

- Two independent parity chains meet at `.claude/agents/`: generated (`templates/agents/*.shared.md` -> `build/generate_agents.py` -> `src/copilot-cli/agents/`, `src/vs-code-agents/`) and hand-copied (`.claude/agents/` <-> `.github/agents/`, enforced by parity + drift checks instead of a generator).
- `instructions/*.instructions.md` and `src/copilot-cli/instructions/*.instructions.md` are two separately generated mirrors of `.claude/rules/`; a rule scoped entirely to internal paths is skipped from the plugin mirror but kept here, so file counts between the two trees need not match.
- `prompts/pr-quality-gate-*.md` is a one-way generation edge from `.claude/skills/review/references/`; `CODEOWNERS` pins both ends under one required review.

## Commands

```bash
# Reproduce the ADR-006 run-block scan pr-validation.yml runs
uv run python scripts/ci/adr006_run_block_scanner.py --max 0
# Reproduce the workflow-schema check (structure, action SHA pinning)
uv run python scripts/validate_workflows.py
# Regenerate Copilot instruction mirrors after a .claude/rules/ edit
uv run python build/scripts/generate_rules.py
# Regenerate pr-quality-gate prompts after a review/references/ edit
uv run python build/scripts/generate_pr_quality_prompts.py
# Check .github/agents/ vs .claude/agents/ parity and semantic drift
uv run python build/scripts/validate_install_parity.py
uv run python build/scripts/detect_agent_drift.py
# Check copilot-instructions.md and root doc byte/token budgets
uv run python -m scripts.validation.passive_context_budget --ci
uv run python -m scripts.validation.instruction_budget --ci
# Full pre-push gate (runs the above plus everything else pre_pr.py owns)
uv run python scripts/validation/pre_pr.py
```
