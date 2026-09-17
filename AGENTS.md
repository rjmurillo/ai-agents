# AGENTS

Serena[BLOCKING]|mcp__serena__activate_project|mcp__serena__initial_instructions|fallback:`.serena/memories/<name>.md`|post:rerun
Retrieve|APIs: C7/DW/Web|memory|constraints: governance|ADRs: architecture|skills/rules: `.claude`|generators: governance
Gates|S: Serena/handoff/resume/memory/git|M: rev count 10/15|P: `pre_pr.py`/no BLOCKING/security/style|E: handoff/Serena/lint/commit/check
Bounds|A: Python ADR-042, branch/skills/PR, lint, pinned Actions, workflows|Ask: architecture/ADR/breaking/security|Guard: reversible internal act, irreversible external confirm, ambiguous minimal + flag|Never: secrets/bash/YAML logic/raw `gh`/force-push/no-verify/internal refs/scratch|Block: artifact test, security fix/owner, conflict resolve, validation pre-PR|no manifest ADR-092
Skills|`.claude/skills/autoplan/SKILL.md`|no skill -> autoplan|multi -> orchestrator|conflict -> GitHub/merge-resolver|CI ladder|new capability: buy-vs-build|harness portability|ADR review

## Model, Effort, and Cost Routing

Cost|route by shape/verifier/failure|accepted-result cost = inference+retry+repair+replay/tool+verifier/review+coordination+human wait|weight judgment/correction > price|down: bounded+cheap+objective+low fan-out+compact receipt|never vendor labels
Luna|low/medium|disposable high-volume discovery, extraction, classification, triage, boilerplate, config, scaffold, docs, exact edits
Haiku|non-reasoning|simple transformations and tool calls
Terra or Sonnet|medium/high or medium|known files/patterns, normal implementation/review, local repair, moderate analysis
Sol or Opus|medium/high|ambiguity, architecture, hard debugging, cross-file reasoning, exceptions, high-recall review, expensive failure
Escalate|failed acceptance test or typed exception|verifier result, never vendor label
Topology|Astra: objective/contract/acceptance|Luna: discovery|Terra: implementation|Sol: exceptions/review|verifier: tests/diff/schema/security|Astra accepts
Astra|delegate, not implement|event-driven waits|return deltas/paths/results/escalation, not transcripts|stop after acceptance
Labels|tiers != agents/IDs|orchestrator coordinates, autoplan routes|roles/mappings/handoffs/ADR-009/078 authoritative|supported -> ID|unresolved -> default + record|no substitution|runtime enforcement not claimed
Contract|objective|scope|verifier|criterion|exception/recipient|receipt: label/ID/paths/result/acceptance/escalation
Exceptions|acceptance_failed|cross_file_contract_missed|repair_repeated|diff_scope_exceeded|Sol only|no prompt escalation
Shape|unclear/high-stakes -> Astra/Sol|bounded/deterministic -> Terra/Luna|architecture/intent/tradeoffs -> do not down|verifier + cheap failure -> Luna|costly diagnosis -> Sol

## Standards

Commits: type(scope): desc + Co-Authored-By|exit: 0/1/2/3/4 = ok/logic/config/external/auth|coverage: security 100%, business 80%, docs 60%|tests: pytest/ruff|blocking: positive/negative/edge/branches/mock I/O/CLI

Stack|Py3.14|pyproject|UV|PS7.5|Node LTS|pytest9|gh2.60
