[build/]
|Generators and drift gates for the agent/skill/rule/hook/settings pipeline. S... (see: .project-toolkit/context/build/details/build.md)
[Matters]
|`build_all.py --check`: drift gate over `_effective_owned_prefixes` (`OWNED_P... (see: .project-toolkit/context/build/details/matters.md)
[Entry points]
|`build_all.py` (`--check`), `generate_agents.py`, `detect_agent_drift.py`. (see: .project-toolkit/context/build/details/entry-points.md)
[Where to look]
|| Path | Why | (see: .project-toolkit/context/build/details/where-to-look.md)
[Skip]
|Generator OUTPUT (`OWNED_PREFIXES`): `src/`, `.github/instructions/`, `.githu... (see: .project-toolkit/context/build/details/skip.md)
[Constraints]
|Order: agents, agent-catalog, adr-index, skills, rules, lib, hooks, then binp... (see: .project-toolkit/context/build/details/constraints.md)
[Dangerous assumptions]
|`scripts/sync_plugin_lib.py` looks like a required first step; it is a deprec... (see: .project-toolkit/context/build/details/dangerous-assumptions.md)
[Dependencies]
|`generate_pr_quality_prompts.py`: `.claude/skills/review/references/<role>.md... (see: .project-toolkit/context/build/details/dependencies.md)
[Architecture]
|Lib (B5): `lib_mirror.py` renders `scripts/{hook_utilities,github_core,ai_rev... (see: .project-toolkit/context/build/details/architecture.md)
[Commands]
|(see detail file) (see: .project-toolkit/context/build/details/commands.md)