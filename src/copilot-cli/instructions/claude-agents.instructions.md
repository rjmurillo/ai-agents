---
applyTo: src/claude/**
---

# Claude Agent and Skill Rules

`src/claude/*.md` are hand-maintained Claude agent prompts with unique Claude-specific content (`name`/`model` frontmatter). They are NOT generated. `templates/agents/*.shared.md` holds the shared body that the Copilot and VS Code copies are generated from; `build/scripts/detect_agent_drift.py` enforces that `src/claude/*.md` does not diverge from that shared body. `.claude/agents/`, `.claude/skills/`, and `.claude/commands/` hold per-repo artifacts loaded by Claude Code.

## MUST

1. **Edit Claude agents directly, in lockstep with the shared template**. `src/claude/*.md` is hand-maintained; no generator writes it (`detect_agent_drift.py:19` "Claude agents ... are NOT generated from templates"). To change shared agent behavior, edit BOTH `src/claude/<agent>.md` AND `templates/agents/<agent>.shared.md` in the same change, then run `python3 build/generate_agents.py` to refresh the generated Copilot/VS Code/Visual Studio copies. `detect_agent_drift.py` fails if `src/claude/*.md` diverges from the shared body.
2. **Skill schema**. Every skill MUST have a `SKILL.md` with frontmatter fields `name`, `version`, `description` per `.agents/steering/claude-skills.md`.
3. **Skill tests**. New skills MUST include pytest or Pester coverage under `.claude/skills/<name>/tests/`.
4. **File cap per PR**. Skill additions SHOULD ship ≤10 files per PR (see `.agents/steering/claude-skills.md`).
5. **No internal references in `src/claude/`**. Files under `src/claude/` MUST NOT reference `.agents/` paths that will not exist for downstream installers.
6. **Python for skill scripts**. New skill scripts MUST be Python per ADR-042.

## SHOULD

1. **One skill, one purpose**. Skills SHOULD do one thing well. Split multi-purpose skills.
2. **Idempotent tools**. Skills that mutate state SHOULD be safe to re-run (or detect prior completion).
3. **Invoke via the Skill tool**. Claude Code agents SHOULD invoke matching skills via the `Skill` tool, not inline equivalents.

## MUST NOT

1. MUST NOT hand-edit generated agent files (`src/copilot-cli/`, `src/vs-code-agents/`, `src/visual-studio/`) to add behavior; add it to the template and regenerate. This does NOT apply to `src/claude/*.md`, which is hand-maintained and edited directly.
2. MUST NOT bundle skill code changes with memory changes in the same PR (separate concerns).

## References

- `build/generate_agents.py`. Generator (emits the Copilot/VS Code/Visual Studio copies only; does NOT write `src/claude/`)
- `build/scripts/detect_agent_drift.py`. Enforces `src/claude/*.md` stays in sync with the shared template body
- `.agents/steering/agent-prompts.md`. Prompt standards
- `.agents/steering/claude-skills.md`. Skill authoring standards
- `.agents/architecture/ADR-042-python-migration-strategy.md`. Python-first
