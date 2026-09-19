[.github/]
|CI workflows plus generated Copilot mirrors, agents, prompts, and hook JSON f... (see: .agents/context/github/details/github.md)
[Matters]
|Generated, never hand-edit: `instructions/`, `agents/*.agent.md`, `hooks/`, a... (see: .agents/context/github/details/matters.md)
[Entry points]
|`workflows/pr-validation.yml`, job `Validate PR`: required check. PR body sha... (see: .agents/context/github/details/entry-points.md)
[Where to look]
|| Path | Why | (see: .agents/context/github/details/where-to-look.md)
[Skip]
|`ISSUE_TEMPLATE/`: unread. `FUNDING.yml`: read only by `labeler.yml`. `CLAUDE... (see: .agents/context/github/details/skip.md)
[Constraints]
|Job bodies live in `scripts/ci/` or `.github/scripts/`, tested in `tests/`. (see: .agents/context/github/details/constraints.md)
[Dangerous assumptions]
|"`instructions/` mirrors `.claude/rules/`": since ADR-109 B2 the generator so... (see: .agents/context/github/details/dangerous-assumptions.md)
[Dependencies]
|Agent render map: `templates/AGENTS.md`. Generator order, `OWNED_PREFIXES`, b... (see: .agents/context/github/details/dependencies.md)
[Architecture]
|`generate_rules.py` writes both mirrors in one run, renaming `paths:` to `app... (see: .agents/context/github/details/architecture.md)
[Commands]
|(see detail file) (see: .agents/context/github/details/commands.md)