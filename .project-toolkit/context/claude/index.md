[.claude/]
|Binplaced dogfood copy of the `project-toolkit` plugin tree (`src/claude/`), ... (see: .project-toolkit/context/claude/details/claude.md)
[Matters]
|Generated, never hand-edit: `agents/`, `rules/`, `skills/<name>/SKILL.md`, `h... (see: .project-toolkit/context/claude/details/matters.md)
[Entry points]
|New rule: `templates/rules/<name>.md` with `paths:` frontmatter; a literal `{... (see: .project-toolkit/context/claude/details/entry-points.md)
[Where to look]
|| Path | Why | (see: .project-toolkit/context/claude/details/where-to-look.md)
[Skip]
|`.gitignore`: excludes `settings.local.json`, `*.local.*` only. (see: .project-toolkit/context/claude/details/skip.md)
[Constraints]
|Every `.md` under `agents/` needs a non-empty `description:`; the loader regi... (see: .project-toolkit/context/claude/details/constraints.md)
[Dangerous assumptions]
|"`rules/`, `agents/`, `skills/<name>/SKILL.md`, `hooks/`, `settings.json`, `l... (see: .project-toolkit/context/claude/details/dangerous-assumptions.md)
[Dependencies]
|`lib/` packages and `bootstrap.py` arrive by binplace from the repo build, on... (see: .project-toolkit/context/claude/details/dependencies.md)
[Architecture]
|`lib/` is both origin and waypoint. (see: .project-toolkit/context/claude/details/architecture.md)
[Commands]
|Repository-only, from the `rjmurillo/ai-agents` root, not shipped: (see: .project-toolkit/context/claude/details/commands.md)