[.agents/]
|Governance, planning, history; no plugin ships it. (see: .project-toolkit/context/agents/details/agents.md)
[Matters]
|Rules auto-load: `session-logs`,`token-economy`->`.agents/**`; `adr-records`,... (see: .project-toolkit/context/agents/details/matters.md)
[Entry points]
|`sessions/handoffs/<date>-<issue>-handoff.md`: read latest, update at end. Si... (see: .project-toolkit/context/agents/details/entry-points.md)
[Where to look]
|| Path | Why | (see: .project-toolkit/context/agents/details/where-to-look.md)
[Skip]
|`sessions/*.json`, `archive/`, `retrospective/` (same-day file gates non-docs... (see: .project-toolkit/context/agents/details/skip.md)
[Constraints]
|`validate-planning-artifacts.yml` fires on `planning/**`: estimate divergence... (see: .project-toolkit/context/agents/details/constraints.md)
[Dangerous assumptions]
|`hooks/hooks.yaml` retired, read by nothing; `hooks/README.md` misnames the l... (see: .project-toolkit/context/agents/details/dangerous-assumptions.md)
[Dependencies]
|`schemas/*.json` gate `skillbook/` JSON (`skillbook-validation.yml`); `tests/... (see: .project-toolkit/context/agents/details/dependencies.md)
[Architecture]
|Distinct trees: `.project-toolkit/skills/` (skillbook learnings), `.project-t... (see: .project-toolkit/context/agents/details/architecture.md)
[Commands]
|(see detail file) (see: .project-toolkit/context/agents/details/commands.md)