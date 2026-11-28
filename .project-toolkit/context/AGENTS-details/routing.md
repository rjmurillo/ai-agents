## Routing

Routing|named skill wins|else `/autoplan` (ADR-078; table in its SKILL.md)|retro->retrospective|lifecycle: spec, plan, build, test, review, ship
Delegate|non-trivial->orchestrator|Explore|implementer/architect/analyst
Install|`~/.claude/` or `.claude/`|no `commands/` (ADR-064)
Rules|read `.claude/rules/*.md` first|source `templates/rules/`|`paths:` only


Cost|route by shape/verifier/failure|price accepted results, not tokens (see orchestrator)|weight judgment/correction > price|down: bounded+cheap+objective+low fan-out+compact receipt|no model/task table, labels advisory
Effort|by task shape+verifier, never vendor default|bounded: lowest|specified: low/medium|judgment: medium, high when ambiguity/repair/architecture/acceptance dominate|more != better, validate per task+harness|pins: ADR-111
Context|goal: system outcomes, not model competence (gov `agent-design-principles`)|script/rule before model|delegate a task worth a brief (inputs fit, result compact), else inline|state in files, pass paths|distill once; read fields, not files|brief AI calls: job/needs/leave alone/return
Tiers|delegation contract -> orchestrator
