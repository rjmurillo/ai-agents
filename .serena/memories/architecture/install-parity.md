# Install-Parity Architecture

## Source-of-truth map

Two distinct flows produce agent and rule artifacts in this repo.

### Canonical → vendored (auto-generated)

- `templates/agents/X.shared.md` is the canonical source of shared agent content. `build/generate_agents.py` emits three vendored copies:
  - `src/claude/X.md` (Claude variant)
  - `src/copilot-cli/agents/X.agent.md` (Copilot variant)
  - `src/vs-code-agents/X.agent.md` (VS Code variant)
- `.claude/skills/`, `.claude/rules/`, `.claude/commands/`, `.claude/hooks/`, `.claude/lib/` are canonical. `build/scripts/build_all.py` propagates them to `src/copilot-cli/*` and (for rules) `.github/instructions/`.
- `REQ-003-010` (asserted in `build_all.py::assert_no_claude_writes`) forbids any generator from writing under `.claude/`. The canonical/install split is intentional.

### Hand-maintained install copies (NOT auto-generated)

- `.claude/agents/X.md`: Claude Code self-host of this repo. Must be edited by hand to match the template.
- `.github/agents/X.agent.md`: GitHub Copilot self-host of this repo. Same hand-edit obligation. Also holds freestanding agents (code-reviewer, silent-failure-hunter, type-design-analyzer, code-simplifier, comment-analyzer, pr-test-analyzer) that have no template.

## Drift class this enables

When a contributor edits `templates/agents/X.shared.md` and regenerates, the vendored `src/*` trees stay in sync but the two hand-maintained install copies do not. Concrete regressions in `main` at time of writing (verified 2026-05-26):

- PR #2087 (qa.shared.md to A tier): missed `.claude/agents/qa.md` and `.github/agents/qa.agent.md`.
- PR #2083 (orchestrator.shared.md to A tier): missed `.claude/agents/orchestrator.md`, `.github/agents/orchestrator.agent.md`, and `src/claude/orchestrator.md`.
- Analyst and critic rewrites: missed `.github/agents/{name}.agent.md`.

## Defense: install-parity validator

`build/scripts/validate_install_parity.py` implements a changed-together check across two parity groups.

- `SHARED_AGENT(name)`: anchored on `templates/agents/{name}.shared.md`. Members are the template, the two install copies, and the three `src/*` vendored copies. All six move together. A `.github/agents/X.agent.md` whose template anchor does not exist is treated as a freestanding one-member group (no false positives for D-tier rewrites).
- `RULE(name)`: anchored on `.claude/rules/{name}.md`. Members are the canonical rule and the two install mirrors under `.github/instructions/` and `src/copilot-cli/instructions/`. Move together.

Skills, commands, hooks, and lib are intentionally out of scope; they are auto-generated and `build/scripts/build_all.py --check` already covers them.

## Defense wiring

- Pre-push: `.claude/hooks/PreToolUse/invoke_install_parity_guard.py` (under the `Bash(git push*)` matcher in `.claude/settings.json`).
- CI: `Install-parity check` step inside `.github/workflows/validate-generated-agents.yml`, runs on every PR that touches the relevant trees.
- Local: `validate_install_parity` registered in `scripts/validation/pre_pr.py` as a non-quick step.
- Tests: `tests/build_scripts/test_validate_install_parity.py` (22 cases).

## Why this matters next time

- A new shared agent must land in six places at once. Forgetting one is now a hard block, not a silent regression discovered weeks later.
- A rule change must land in three places at once. Same gate.
- A new freestanding `.github/agents/X.agent.md` (no template) is allowed without siblings; the validator only enforces parity when a shared anchor exists.

Refs: issue #2094 (defense PR), PR #2087 / PR #2083 (motivating regressions), ADR-035 (exit codes), REQ-003-010 (build_all.py invariant).
