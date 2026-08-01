---
applyTo: src/claude/**
---

# Claude Agent and Skill Rules

`src/claude/*.md` are hand-maintained Claude agent prompts with unique Claude-specific content (`name`/`model` frontmatter). They are NOT generated. `templates/agents/*.shared.md` holds the shared body that the Copilot and VS Code copies are generated from; `build/scripts/detect_agent_drift.py` detects when `src/claude/*.md` diverges from the VS Code copies (`src/vs-code-agents/`), not from the templates directly. `.claude/agents/`, `.claude/skills/`, and `.claude/commands/` hold per-repo artifacts loaded by Claude Code.

## MUST

1. **Edit Claude agents directly, in lockstep with the shared template**. `src/claude/*.md` is hand-maintained; no generator writes it (`detect_agent_drift.py:19` "Claude agents ... are NOT generated from templates"). To change shared agent behavior, edit BOTH `src/claude/<agent>.md` AND `templates/agents/<agent>.shared.md` in the same change, then run `python3 build/generate_agents.py` to refresh the generated Copilot and VS Code copies (`src/copilot-cli/`, `src/vs-code-agents/`). `detect_agent_drift.py` flags divergence between `src/claude/*.md` and the VS Code copies (`src/vs-code-agents/`); it runs weekly via `drift-detection.yml`, not as a PR gate on template edits.
2. **Skill schema**. Every skill MUST have a `SKILL.md` with frontmatter fields `name`, `version`, `description` per `.agents/steering/claude-skills.md`.
3. **Skill tests**. New skills MUST include pytest coverage under `.claude/skills/<name>/tests/`.
4. **File cap per PR**. Skill additions SHOULD ship ≤10 files per PR (see `.agents/steering/claude-skills.md`).
5. **No internal references in `src/claude/`**. Files under `src/claude/` MUST NOT reference `.agents/` paths that will not exist for downstream installers.
6. **Python for skill scripts**. New skill scripts MUST be Python per ADR-042.
7. **Test what the prose promises**. When a `SKILL.md` names a script, an exit code, and what that code means, it has defined an executable contract, and at least one file under `tests/` MUST assert the documented exit-code behavior. Prose is not enforcement: a documented exit code that nothing asserts drifts from the script the first time someone edits the script and not the document, and the drift is invisible because the document still reads correctly. `check_skill_contract_tests.py` enforces this.

## SHOULD

1. **One skill, one purpose**. Skills SHOULD do one thing well. Split multi-purpose skills.
2. **Idempotent tools**. Skills that mutate state SHOULD be safe to re-run (or detect prior completion).
3. **Invoke via the Skill tool**. Claude Code agents SHOULD invoke matching skills via the `Skill` tool, not inline equivalents.

## MUST NOT

1. MUST NOT hand-edit generated agent files (`src/copilot-cli/`, `src/vs-code-agents/`) to add behavior; add it to the template and regenerate. This does NOT apply to `src/claude/*.md`, which is hand-maintained and edited directly.
2. MUST NOT bundle skill code changes with memory changes in the same PR (separate concerns).

## References

- `build/generate_agents.py`. Generator (emits the Copilot and VS Code copies `src/copilot-cli/`, `src/vs-code-agents/` only; does NOT write `src/claude/`)
- `build/scripts/detect_agent_drift.py`. Compares `src/claude/*.md` against VS Code copies (`src/vs-code-agents/`); runs weekly via `.github/workflows/drift-detection.yml`
- `.agents/steering/agent-prompts.md`. Prompt standards
- `.agents/steering/claude-skills.md`. Skill authoring standards
- `scripts/validation/check_skill_contract_tests.py`. Enforces the executable-contract test requirement
- `.agents/architecture/ADR-042-python-migration-strategy.md`. Python-first
- Issue #3402. worktree identity and stale helper resolution
