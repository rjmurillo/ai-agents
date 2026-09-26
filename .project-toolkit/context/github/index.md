[.github/]
|CI workflows plus generated Copilot mirrors, agents, prompts, and hook JSON f... (see: .project-toolkit/context/github/details/github.md)
[Matters]
|Generated, never hand-edit: `instructions/`, `agents/*.agent.md`, `hooks/`, a... (see: .project-toolkit/context/github/details/matters.md)
[Entry points]
|`workflows/pr-validation.yml`, job `Validate PR`: required check. PR body sha... (see: .project-toolkit/context/github/details/entry-points.md)
[Where to look]
|| Path | Why | (see: .project-toolkit/context/github/details/where-to-look.md)
[Skip]
|`ISSUE_TEMPLATE/`: unread. `FUNDING.yml`: read only by `labeler.yml`. `CLAUDE... (see: .project-toolkit/context/github/details/skip.md)
[Constraints]
|Job bodies live in `scripts/ci/` or `.github/scripts/`, tested in `tests/`. (see: .project-toolkit/context/github/details/constraints.md)
[Dangerous assumptions]
|"`instructions/` mirrors `.claude/rules/`": since ADR-109 B2 the generator so... (see: .project-toolkit/context/github/details/dangerous-assumptions.md)
[Dependencies]
|Agent render map: `templates/AGENTS.md`. Generator order, `OWNED_PREFIXES`, b... (see: .project-toolkit/context/github/details/dependencies.md)
[Architecture]
|`generate_rules.py` writes both mirrors in one run, renaming `paths:` to `app... (see: .project-toolkit/context/github/details/architecture.md)
[Commands]
|(see detail file) (see: .project-toolkit/context/github/details/commands.md)