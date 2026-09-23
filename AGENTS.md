# AGENTS

Serena[BLOCKING]|mcp__serena__activate_project|mcp__serena__initial_instructions|fallback:`.serena/memories/<name>.md`|post:rerun
Knowledge -> context|C7/DW/Web|mem|constraints gov|ADRs arch|skills/rules .claude|generators gov
Gates|S init/handoff/resume/memory/git|P `pre_pr.py`/no BLOCKING/security/style|E handoff/Serena/lint/commit/check
**Always**: Python ADR-042|branch/skills/PR/lint|SHA Actions|workflows|No manifest version (ADR-092)
**Ask First**: architecture/ADR/breaking/security
**Autonomy Guardrail**: reversible internal|irreversible external|ambiguous minimal+flag
**Never**: Secrets|New bash scripts|YAML logic|Raw `gh`|Force-push|No-verify|Internal refs|Scratch
Block|artifact->test|security->fix/owner|conflict->resolve|validation->pre-PR
Skills|route autoplan|no skill -> autoplan|multi -> orchestrator|conflict -> GitHub/merge-resolver|CI ladder|new cap buy-vs-build|agent-harness-reference|ai-agents-portability-campaign|ADR review

## Routing

Cost|route by shape/verifier/failure|accepted-result cost = inference+retry+repair+replay/tool+verifier/review+coordination+human wait|weight judgment/correction > price|down: bounded+cheap+objective+low fan-out+compact receipt|never vendor labels
Fable 5.1|escalation after higher-effort Opus fails|highest stakes, long-horizon, architecture, complex research, consequential analysis
Opus 5.5|default frontier|agentic coding, broad context, knowledge work, computer use, research, end-to-end judgment
GPT-6 Astra|ambiguous, consequential|architecture, research, complex coding, documents, computer use, acceptance
Sonnet 5/GPT-6/5.6 Sol|specified judgment|coding, doc review, fact checking, structured research
Haiku 4.5/GPT-6/5.6 Luna|bounded, checkable|extraction, classification, triage, summaries, small edits, routing, volume
GPT-5.6 Terra|known patterns|implementation/review, repair
Effort|lightest passing acceptance, not vendor default|raise at unresolved judgment|Opus before Fable
Orchestrator|delegates, not implements|event-driven waits|deltas/paths/results/escalation, not transcripts|stop after acceptance
Labels|tiers != agents/IDs|orchestrator coordinates, autoplan routes|roles/mappings/handoffs/ADR-009/078 authoritative|supported -> ID|unresolved -> default + record|no substitution|no enforcement
Contract|objective|scope|verifier|criterion|exception/recipient|receipt: label/ID/paths/result/acceptance/escalation
Exceptions|acceptance_failed|cross_file_contract_missed|repair_repeated|diff_scope_exceeded|Sol/Opus only|no prompt escalation
Shape|unclear/high-stakes -> Opus/Astra|specified -> Sonnet/Sol|checkable -> Haiku/Luna|known -> Terra|verify: tests/diff/schema/security

## Standards

Commits: type(scope): desc + Co-Authored-By|exit: 0/1/2/3/4 = ok/logic/config/external/auth|coverage: security 100%, business 80%, docs 60%|tests: pytest/ruff|blocking: positive/negative/edge/branches/mock I/O/CLI

Stack|Py3.14|pyproject|UV|PS7.5|Node LTS|pytest9|gh2.60
