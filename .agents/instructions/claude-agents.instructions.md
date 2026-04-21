---
applyTo: "src/claude/**,.claude/agents/**,.claude/skills/**,.claude/commands/**"
priority: high
---

# Claude Agent and Skill Rules

`src/claude/` holds Claude-specific agent prompts generated from `templates/`. `.claude/agents/`, `.claude/skills/`, and `.claude/commands/` hold per-repo artifacts loaded by Claude Code.

## MUST

1. **Templates are source of truth** — MUST NOT edit `src/claude/*.md` directly. Edit the matching template in `templates/agents/` and regenerate with `python3 build/generate_agents.py`.
2. **Skill schema** — Every skill MUST have a `SKILL.md` with frontmatter fields `name`, `version`, `description` per `.agents/steering/claude-skills.md`.
3. **Skill tests** — New skills MUST include pytest or Pester coverage under `.claude/skills/<name>/tests/`.
4. **File cap per PR** — Skill additions SHOULD ship ≤10 files per PR (see `.agents/steering/claude-skills.md`).
5. **No internal references in `src/claude/`** — Generated files MUST NOT reference `.agents/` paths that will not exist for downstream installers.
6. **Python for skill scripts** — New skill scripts MUST be Python per ADR-042.

## SHOULD

1. **One skill, one purpose** — Skills SHOULD do one thing well. Split multi-purpose skills.
2. **Idempotent tools** — Skills that mutate state SHOULD be safe to re-run (or detect prior completion).
3. **Invoke via the Skill tool** — Claude Code agents SHOULD invoke matching skills via the `Skill` tool, not inline equivalents.

## MUST NOT

1. MUST NOT hand-edit generated agent files to add behavior; add it to the template.
2. MUST NOT bundle skill code changes with memory changes in the same PR (separate concerns).

## References

- `build/generate_agents.py` — generator
- `.agents/steering/agent-prompts.md` — prompt standards
- `.agents/steering/claude-skills.md` — skill authoring standards
- `.agents/architecture/ADR-042-python-migration-strategy.md` — Python-first
- `.github/instructions/claude-skills.instructions.md` — Copilot entry point
