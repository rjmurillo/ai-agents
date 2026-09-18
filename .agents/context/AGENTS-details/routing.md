## Routing

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
