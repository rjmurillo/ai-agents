[src/]
|Both marketplace plugin sources: `claude/` for Claude Code, `copilot-cli/` fo... (see: .agents/context/src/details/src.md)
[Matters]
|ADR-109 B1 to B5: `claude/{agents,skills,rules,hooks}` and `claude/hooks.json... (see: .agents/context/src/details/matters.md)
[Entry points]
|Claude/Copilot agent: edit BOTH `templates/agents/<stem>.claude.md.tmpl` AND ... (see: .agents/context/src/details/entry-points.md)
[Where to look]
|| Path | Why | (see: .agents/context/src/details/where-to-look.md)
[Skip]
|`claude/{agents,skills,rules,hooks,lib}/`, `copilot-cli/{agents,skills,instru... (see: .agents/context/src/details/skip.md)
[Constraints]
|Regenerate, verify `--check`, commit source and output together. (see: .agents/context/src/details/constraints.md)
[Dangerous assumptions]
|`copilot-cli/docs/copilot-instructions.md` looks generated; hand-authored, no... (see: .agents/context/src/details/dangerous-assumptions.md)
[Dependencies]
|`copilot-cli/lib/` and `claude/lib/`: rendered from `scripts/` packages by `b... (see: .agents/context/src/details/dependencies.md)
[Architecture]
|Render pipeline and gate semantics: `build/AGENTS.md`. (see: .agents/context/src/details/architecture.md)
[Commands]
|(see detail file) (see: .agents/context/src/details/commands.md)