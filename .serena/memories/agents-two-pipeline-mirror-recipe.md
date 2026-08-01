# Two-Pipeline Agent Mirror Recipe (#2707)

## Recipe

To change shared agent behavior, edit BOTH of these in the same change, then regenerate:

1. `src/claude/<agent>.md` , the hand-maintained Claude agent prompt (carries Claude-specific `name`/`model` frontmatter). NOT generated; edit directly.
2. `templates/agents/<agent>.shared.md` , the shared body the Copilot CLI and VS Code copies are generated from.

Then run `python3 build/generate_agents.py` to refresh the generated copies (`src/copilot-cli/agents/`, `src/vs-code-agents/`).

`build/scripts/detect_agent_drift.py` compares `src/claude/<agent>.md` against the VS Code copies in `src/vs-code-agents/` (NOT against the templates). It flags when the two diverge significantly. The comparison runs weekly via `.github/workflows/drift-detection.yml`. Do NOT hand-edit the generated `src/copilot-cli/` or `src/vs-code-agents/` copies (canonical-source-mirror rule); add behavior to the template and regenerate.

## Why (evidence)

Issue #2707 shipped SkillOpt determinism fixes for `silent-failure-hunter` (an AGENT, alongside two skills). The agent fix required this two-pipeline edit; getting it wrong trips the drift gate. Contrasts with skills, which are single-source under `.claude/skills/` and mirrored to `src/copilot-cli/skills/` via `build/scripts/generate_skills.py` (directory-copy), and with slash commands (generate_commands.py).

## Apply when

Editing any agent's shared behavior. See `.claude/rules/claude-agents.md` MUST-1 for the binding rule.

Source: issue/PR #2707 (MERGED); `.claude/rules/claude-agents.md`; `build/scripts/detect_agent_drift.py`.
