## Routing

Cost|route by shape/verifier/failure|accepted-result cost = inference+retry+repair+replay/tool+verifier/review+coordination+human wait|weight judgment/correction > price|down: bounded+cheap+objective+low fan-out+compact receipt|never vendor labels
GPT-6 Astra|ambiguous, consequential, broad-context, multi-tool|architecture, research, complex coding, documents, computer use, end-to-end acceptance
GPT-6/5.6 Sol|specified demanding|everyday coding, technical research, fact checking, document review, judgment-heavy agentic work
GPT-6/5.6 Luna|bounded, frequent, externally checkable|extraction, classification, triage, small edits, repeated transforms, volume automation
GPT-5.6 Terra/Sonnet|known patterns|implementation/review, repair
Haiku|non-reasoning|simple transforms/tool calls
Effort|lightest passing acceptance|raise only at unresolved judgment; failure/typed exception triggers escalation
Topology|Astra: objective/acceptance|Luna: bounded work|Terra: implementation|Sol: judgment/review|verifier: tests/diff/schema/security
Orchestrator|delegates, not implements|event-driven waits|deltas/paths/results/escalation, not transcripts|stop after acceptance
Labels|tiers != agents/IDs|orchestrator coordinates, autoplan routes|roles/mappings/handoffs/ADR-009/078 authoritative|supported -> ID|unresolved -> default + record|no substitution|no enforcement
Contract|objective|scope|verifier|criterion|exception/recipient|receipt: label/ID/paths/result/acceptance/escalation
Exceptions|acceptance_failed|cross_file_contract_missed|repair_repeated|diff_scope_exceeded|Sol only|no prompt escalation
Shape|unclear/high-stakes -> Astra|specified judgment -> Sol|bounded/checkable -> Luna|known patterns -> Terra
