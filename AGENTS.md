# AGENTS

Memory|recall: `memory-search`|change: `memory-gate`|retain: `memory`|scoped tools or repo files|repo: `.serena/memories/`|verify recalled facts|no secrets
Serena|init once if available|`.mcp.json --project` activates at start|LSP first (`using-serena-symbols`), else local search
Knowledge -> context|C7/DW/Web|mem|constraints gov|ADRs arch|skills/rules .claude|generators gov
Gates|S init/handoff/resume/memory/git|P `pre_pr.py`/no BLOCKING/security/style|E handoff/memory/lint/commit/check
**Always**: Python ADR-042|branch/skills/PR/lint|SHA Actions|workflows|No manifest version (ADR-092)|skill/agent->page or Docs-Reviewed
**Ask First**: architecture/ADR/breaking/security
**Autonomy Guardrail**: tiers ADR-112|irreversible->human|ambiguous minimal+flag
**Never**: Secrets|New bash scripts|YAML logic|Raw `gh`|Force-push|No-verify|Internal refs|Scratch
Setup|one command: `CONTRIBUTING.md` Setup Steps|non-root only
Disk|wt: `~/worktrees/<repo>/<branch>`|scratch: wt `.project-toolkit/scratch/`|done: remove wt+branch
Drive-by|default no|`avoiding-manufactured-work`
Block|artifact->test|security->fix/owner|conflict->resolve|validation->pre-PR
Skills|route autoplan|no skill -> autoplan|multi -> orchestrator|conflict -> GitHub/merge-resolver|CI ladder|new cap buy-vs-build|agent-harness-reference|ai-agents-portability-campaign|ADR review: log non-frontmatter edits; full panel for executable enforcement or rules gates read, else architect+critic

## Routing

Routing|named skill wins|else `/autoplan` (ADR-078; table in its SKILL.md)|retro->retrospective|lifecycle: spec, plan, build, test, review, ship
Delegate|non-trivial->orchestrator|Explore|implementer/architect/analyst
Install|`~/.claude/` or `.claude/`|no `commands/` (ADR-064)
Rules|read `.claude/rules/*.md` first|source `templates/rules/`|`paths:` only

Cost|route by shape/verifier/failure|price accepted results, not tokens (see orchestrator)|weight judgment/correction > price|down: bounded+cheap+objective+low fan-out+compact receipt|no model/task table; advisory labels
Effort|by task shape+verifier, never vendor default|bounded: lowest|specified: low/medium|judgment: medium, high when ambiguity/repair/architecture/acceptance dominate|more != better, validate per task+harness|pins: ADR-080
Context|goal: system outcomes, not model competence (gov `agent-design-principles`)|script/rule before model|delegate a task worth a brief (inputs fit, result compact), else inline|state in files, pass paths|distill once; read fields, not files|brief AI calls: job/needs/leave alone/return
Tiers|delegation contract -> orchestrator

## Standards

Commits: type(scope): desc + Co-Authored-By|exit: 0/1/2/3/4 = ok/logic/config/external/auth|coverage: security 100%, business 80%, docs 60%|tests: pytest/ruff|blocking: positive/negative/edge/branches/mock I/O/CLI

Stack|Py3.14|pyproject|UV|PS7.5|Node LTS|pytest9|gh2.60
