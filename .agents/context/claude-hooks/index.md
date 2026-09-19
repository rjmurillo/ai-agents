[.claude/hooks/]
|Claude Code lifecycle hooks: generated output, run by the harness, mirrored i... (see: .agents/context/claude-hooks/details/claudehooks.md)
[Matters]
|Generated from `templates/hooks/`; edit the template, not this tree. Render m... (see: .agents/context/claude-hooks/details/matters.md)
[Entry points]
|`invoke_dispatch_claude.py --group <id>`: reads that group's shims and `mode`... (see: .agents/context/claude-hooks/details/entry-points.md)
[Where to look]
|| Path | Why | (see: .agents/context/claude-hooks/details/where-to-look.md)
[Skip]
|`PostToolUse/README.md`: authoring template for a class with zero scripts; it... (see: .agents/context/claude-hooks/details/skip.md)
[Constraints]
|A hand edit here is overwritten by the next build and fails the pre-PR row `G... (see: .agents/context/claude-hooks/details/constraints.md)
[Dangerous assumptions]
|`PreToolUse/_bootstrap.py` looks dead. The Copilot dispatcher generator copie... (see: .agents/context/claude-hooks/details/dangerous-assumptions.md)
[Dependencies]
|Copilot mirror `src/copilot-cli/hooks/` renders from `src/claude/hooks.json` ... (see: .agents/context/claude-hooks/details/dependencies.md)
[Architecture]
|One protocol-valid stdout document per group: context parts join on a blank l... (see: .agents/context/claude-hooks/details/architecture.md)
[Commands]
|Run only in the `rjmurillo/ai-agents` checkout, not a consumer install. (see: .agents/context/claude-hooks/details/commands.md)