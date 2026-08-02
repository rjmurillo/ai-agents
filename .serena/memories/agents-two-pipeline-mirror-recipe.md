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

No check compares `src/claude/<agent>.md` against the shared body in `templates/agents/<agent>.shared.md`. `build/scripts/detect_agent_drift.py` never reads a template body; it scores `src/claude` against `src/vs-code-agents` over an 18-section allowlist, and it is a similarity floor (default 80), not an equality check. What enforces the lockstep is co-change in a diff (`build/scripts/validate_install_parity.py`), so the two must move together in the same PR diff. Do NOT hand-edit the generated `src/copilot-cli/` or `src/vs-code-agents/` copies (canonical-source-mirror rule); add behavior to the template and regenerate.

## Why (evidence)

Issue #2707 shipped SkillOpt determinism fixes for `silent-failure-hunter` (an AGENT, alongside two skills). The agent fix required this two-pipeline edit. Getting it wrong is NOT caught by the drift gate: `silent-failure-hunter` matches zero allowlisted sections, so `detect_agent_drift.py` returns a hardcoded 100.0 for it whatever the file contains (verified 2026-08-01 at `7e8d3ac2f4` by replacing its entire generated body with one unrelated sentence: still RC=0 / 100.0 / OK). Co-change parity is the only check watching that pair. Contrasts with skills, which are single-source under `.claude/skills/` and mirrored to `src/copilot-cli/skills/` via `build/scripts/generate_skills.py` (directory-copy), and with slash commands (generate_commands.py).

## Apply when

Editing any agent's shared behavior. See `.claude/rules/claude-agents.md` MUST-1 for the binding rule.

Source: issue/PR #2707 (MERGED); `.claude/rules/claude-agents.md`; `build/scripts/detect_agent_drift.py`.
