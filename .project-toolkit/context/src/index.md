[src/]
|Both marketplace plugin sources: `claude/` for Claude Code, `copilot-cli/` fo... (see: .project-toolkit/context/src/details/src.md)
[Matters]
|ADR-109: `claude/{agents,skills,rules,hooks}` render from `templates/`. Dogfo... (see: .project-toolkit/context/src/details/matters.md)
[Entry points]
|Claude/Copilot agent: edit BOTH `templates/agents/<stem>.claude.md.tmpl` AND ... (see: .project-toolkit/context/src/details/entry-points.md)
[Where to look]
|| Path | Why | (see: .project-toolkit/context/src/details/where-to-look.md)
[Skip]
|`claude/{agents,skills,rules,hooks}/`, `copilot-cli/{agents,skills,instructio... (see: .project-toolkit/context/src/details/skip.md)
[Constraints]
|Regenerate, verify `--check`, commit source and output together. (see: .project-toolkit/context/src/details/constraints.md)
[Dangerous assumptions]
|`copilot-cli/docs/copilot-instructions.md` looks generated; hand-authored, no... (see: .project-toolkit/context/src/details/dangerous-assumptions.md)
[Dependencies]
|`build_all.py` renders lib packages and bootstrap from `scripts/`. See `.clau... (see: .project-toolkit/context/src/details/dependencies.md)
[Architecture]
|Render pipeline and gate semantics: `build/AGENTS.md`. (see: .project-toolkit/context/src/details/architecture.md)
[Commands]
|(see detail file) (see: .project-toolkit/context/src/details/commands.md)