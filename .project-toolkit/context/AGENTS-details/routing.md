## Routing

Skill routing|named skill or its slash command wins|no skill named -> `/autoplan` (ADR-078; routes to skills, lifecycle skills, agents; table lives in `.claude/skills/autoplan/SKILL.md` only)|retro trigger -> retrospective
Lifecycle|requirements -> spec|plan, break down, estimate -> plan|implement -> build|test, debug -> test|review -> review|ship, push, PR -> ship
Delegate|non-trivial -> orchestrator subagent|exploration -> Explore|focused -> implementer, architect, analyst
Install|global `~/.claude/agents/`, `~/.claude/skills/`|per-repo `.claude/agents/`, `.claude/skills/`|ADR-064: skills are the only user-invocable surface; a validator blocks `.claude/commands/` files
Rules|before an edit read matching `.claude/rules/*.md`|edit `templates/rules/<name>.md`, then `uv run python build/scripts/build_all.py` (also writes `.github/instructions/`, `src/copilot-cli/instructions/`)|scope key `paths:` only (`check_rule_scope_keys.py`)

Cost|route by shape/verifier/failure|price accepted results, not tokens (see orchestrator)|weight judgment/correction > price|down: bounded+cheap+objective+low fan-out+compact receipt|no model/task table, labels advisory
Effort|by task shape+verifier, never vendor default|bounded: lowest|specified: low/medium|judgment: medium, high when ambiguity/repair/architecture/acceptance dominate|more != better, validate per task+harness|pins: ADR-080
Context|goal: system outcomes, not model competence (gov `agent-design-principles`)|script/rule before model|delegate a task worth a brief (inputs fit, result compact), else inline|state in files, pass paths|distill once; read fields, not files|brief AI calls: job/needs/leave alone/return
Tiers|delegation contract -> orchestrator
