<!-- placement: evidence; reason: the PR #395 scope-blowout measurement, kept as the observation behind scope discipline -->

# Orchestration: What an Unbounded Debug Prompt Cost in PR #395

Authoritative owners: `.claude/rules/builder-ethos.md` Task Completion Contract
defines what keeps a task active, and `AGENTS.md` Autonomy Guardrail sets the
boundary for an ambiguous request.

## Measurement (2025-12-25, PR #395)

A Copilot agent was asked to debug a script that "ran but did nothing".

| Signal | Value |
|---|---|
| Expected change | about 50 lines, a visibility fix |
| Actual change | 847 lines |
| Outcome | the script was broken by the change |
| Root cause | the prompt carried no scope constraint |

The expansion came from work nobody asked for: dead-code removal during a debug
task, logging beyond the reported symptom, and changed function signatures.

## Transferable reading

A debug request names a symptom, not a scope. Without a stated ceiling, an
agent treats every adjacent defect it notices as in scope, and the diff grows
past the point where a reviewer can tell the fix from the collateral.

## Related

- [orchestration-003-orchestrator-first-routing](orchestration-003-orchestrator-first-routing.md)
- [orchestration-copilot-swe-anti-patterns](orchestration-copilot-swe-anti-patterns.md)
- [orchestration-prompt-002-copilot-swe-constraints](orchestration-prompt-002-copilot-swe-constraints.md)
