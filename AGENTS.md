# AGENTS

Serena[BLOCKING]|mcp__serena__activate_project|mcp__serena__initial_instructions|fallback:`.serena/memories/<name>.md`|post:rerun
Knowledge -> context|C7/DW/Web|mem|constraints gov|ADRs arch|skills/rules .claude|generators gov
Gates|S init/handoff/resume/memory/git|P `pre_pr.py`/no BLOCKING/security/style|E handoff/Serena/lint/commit/check
**Always**: Python ADR-042|branch/skills/PR/lint|SHA Actions|workflows|No manifest version (ADR-092)
**Ask First**: architecture/ADR/breaking/security
**Autonomy Guardrail**: tiers ADR-112|irreversible->human|ambiguous minimal+flag
**Never**: Secrets|New bash scripts|YAML logic|Raw `gh`|Force-push|No-verify|Internal refs|Scratch
Block|artifact->test|security->fix/owner|conflict->resolve|validation->pre-PR
Skills|route autoplan|no skill -> autoplan|multi -> orchestrator|conflict -> GitHub/merge-resolver|CI ladder|new cap buy-vs-build|agent-harness-reference|ai-agents-portability-campaign|ADR review

## Routing

Cost|route by shape/verifier/failure|accepted-result cost = inference+retry+repair+replay/tool+verifier/review+coordination+human wait|weight judgment/correction > price|down: bounded+cheap+objective+low fan-out+compact receipt|never vendor labels
Tiers|effort|delegation contract|typed exceptions -> orchestrator agent, Model, Effort, and Cost Routing|intent -> autoplan

## Standards

Commits: type(scope): desc + Co-Authored-By|exit: 0/1/2/3/4 = ok/logic/config/external/auth|coverage: security 100%, business 80%, docs 60%|tests: pytest/ruff|blocking: positive/negative/edge/branches/mock I/O/CLI

Stack|Py3.14|pyproject|UV|PS7.5|Node LTS|pytest9|gh2.60
