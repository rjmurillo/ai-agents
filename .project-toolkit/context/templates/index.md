[templates/]
|Canonical source for five ADR-109 artifact classes: agents, rules, skills, ho... (see: .project-toolkit/context/templates/details/templates.md)
[Matters]
|Per-class render map. Compilers run inside `build_all.py` except `prompts`; b... (see: .project-toolkit/context/templates/details/matters.md)
[Entry points]
|`uv run python build/scripts/build_all.py` renders every class but `prompts` ... (see: .project-toolkit/context/templates/details/entry-points.md)
[Where to look]
|| Path | Why | (see: .project-toolkit/context/templates/details/where-to-look.md)
[Skip]
|Generated, never hand-edited (source is `templates/` except `src/claude/lib`,... (see: .project-toolkit/context/templates/details/skip.md)
[Constraints]
|`validate_templates_schema.py` validates only a `platforms/*.yaml` carrying a... (see: .project-toolkit/context/templates/details/constraints.md)
[Dangerous assumptions]
|`.claude/rules/templates.md` renders from `rules/templates.md` and is stale: ... (see: .project-toolkit/context/templates/details/dangerous-assumptions.md)
[Dependencies]
|Generator order, `OWNED_PREFIXES`, the binplace step, gate semantics, the lib... (see: .project-toolkit/context/templates/details/dependencies.md)
[Architecture]
|`vscode.yaml` and `visual-studio.yaml` both target `src/vs-code-agents`. (see: .project-toolkit/context/templates/details/architecture.md)
[Commands]
|(see detail file) (see: .project-toolkit/context/templates/details/commands.md)