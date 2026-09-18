[.agents/]
|Governance, planning, history; no plugin ships it. (see: .agents/context/agents/details/agents.md)
[Matters]
|Rules auto-load: `session-logs`,`token-economy`->`.agents/**`; `adr-records`,... (see: .agents/context/agents/details/matters.md)
[Entry points]
|`sessions/handoffs/<date>-<issue>-handoff.md`: read latest, update at end. Si... (see: .agents/context/agents/details/entry-points.md)
[Where to look]
|| Path | Why | (see: .agents/context/agents/details/where-to-look.md)
[Skip]
|`sessions/*.json`, `archive/`, `retrospective/` (same-day file gates non-docs... (see: .agents/context/agents/details/skip.md)
[Constraints]
|`validate-planning-artifacts.yml` fires on `planning/**`: estimate divergence... (see: .agents/context/agents/details/constraints.md)
[Dangerous assumptions]
|`hooks/hooks.yaml` retired, read by nothing; `hooks/README.md` misnames the l... (see: .agents/context/agents/details/dangerous-assumptions.md)
[Dependencies]
|`schemas/*.json` gate `skillbook/` JSON (`skillbook-validation.yml`); `tests/... (see: .agents/context/agents/details/dependencies.md)
[Architecture]
|Distinct trees: `skills/` (steering learnings), `skillbook/` (policy/tension/... (see: .agents/context/agents/details/architecture.md)
[Commands]
|(see detail file) (see: .agents/context/agents/details/commands.md)