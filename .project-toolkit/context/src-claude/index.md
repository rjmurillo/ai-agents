[src/claude/]
|`project-toolkit` plugin source (ADR-109 B6; `claude-agents` retired) in the ... (see: .project-toolkit/context/src-claude/details/srcclaude.md)
[Matters]
|Generated (ADR-109 B1 to B4): `agents/` 31, `rules/` 28, `skills/<name>/SKILL... (see: .project-toolkit/context/src-claude/details/matters.md)
[Entry points]
|`templates/agents|rules|skills|hooks/` is the edit location; per-class render... (see: .project-toolkit/context/src-claude/details/entry-points.md)
[Where to look]
|| Path | Why | (see: .project-toolkit/context/src-claude/details/where-to-look.md)
[Skip]
|`.claude/agents/`, `.claude/rules/`, `.claude/skills/<name>/SKILL.md`, `.clau... (see: .project-toolkit/context/src-claude/details/skip.md)
[Constraints]
|Cross-harness change: read `agent-harness-reference` first, route through `ai... (see: .project-toolkit/context/src-claude/details/constraints.md)
[Dangerous assumptions]
|A green `detect_agent_drift.py` proves nothing about `src/vs-code-agents/` pa... (see: .project-toolkit/context/src-claude/details/dangerous-assumptions.md)
[Dependencies]
|Marketplace entry `project-toolkit`, `source: ./src/claude` (B6); `.claude/` ... (see: .project-toolkit/context/src-claude/details/dependencies.md)
[Architecture]
|A render stage, not a source. (see: .project-toolkit/context/src-claude/details/architecture.md)
[Commands]
|(see detail file) (see: .project-toolkit/context/src-claude/details/commands.md)