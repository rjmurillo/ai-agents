# Two-Pipeline Agent Mirror Recipe (#2707)

## Recipe

To change shared agent behavior, edit the template plus all three
hand-maintained copies in the same change, then regenerate:

1. `templates/agents/<agent>.shared.md` , the shared body the Copilot CLI and VS Code copies are generated from. Edit this first.
2. `src/claude/<agent>.md` , hand-maintained Claude agent prompt (carries Claude-specific `name`/`model` frontmatter). NOT generated; edit directly.
3. `.claude/agents/<agent>.md` , hand-maintained Claude Code copy. NOT generated; edit directly.
4. `.github/agents/<agent>.agent.md` , hand-maintained GitHub Copilot self-host copy. NOT generated; edit directly.

Correction verified 2026-07-31: this recipe previously named only items 1 and 2.
Omitting items 3 and 4 is how PR #1715 shipped an orchestrator section to the
Claude copies and never to Copilot. Negative control: revert only
`.claude/agents/orchestrator.md` to `origin/main`, run `build_all.py` (exit 0),
and the reverted content stays reverted. See
`.serena/memories/decision-agent-files-are-not-canonical.md`.

Then run `python3 build/generate_agents.py` to refresh the generated copies (`src/copilot-cli/agents/`, `src/vs-code-agents/`).

`build/scripts/detect_agent_drift.py` FAILS if `src/claude/<agent>.md` diverges from the shared body in `templates/agents/<agent>.shared.md`. So the two must move in lockstep. Do NOT hand-edit the generated `src/copilot-cli/` or `src/vs-code-agents/` copies (canonical-source-mirror rule); add behavior to the template and regenerate.

## Why (evidence)

Issue #2707 shipped SkillOpt determinism fixes for `silent-failure-hunter` (an AGENT, alongside two skills). The agent fix required this two-pipeline edit; getting it wrong trips the drift gate. Contrasts with skills, which are single-source under `.claude/skills/` and mirrored to `src/copilot-cli/skills/` via `build/scripts/generate_skills.py` (directory-copy), and with slash commands (generate_commands.py).

## Apply when

Editing any agent's shared behavior. See `.claude/rules/claude-agents.md` MUST-1 for the binding rule.

Source: issue/PR #2707 (MERGED); `.claude/rules/claude-agents.md`; `build/scripts/detect_agent_drift.py`.
