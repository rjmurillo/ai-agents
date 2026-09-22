<!-- placement: evidence; reason: a 24-session measurement of handoff compliance, kept as the evidence behind gate design, not as a procedure -->

# Orchestration: Handoff Compliance Measured Across 24 Sessions

Authoritative owner: `.claude/agents/orchestrator.md` "Handoff Contract" defines
what a handoff carries today. `.claude/rules/session-logs.md` states that
session log creation is discontinued, so the checklist this measurement scored
no longer exists.

## Measurement (2025-12-20, 24-session analysis)

- 23 of 24 agents handed off to the orchestrator with the Session End checklist
  incomplete.
- Session Start compliance was 79%, enforced by blocking gates.
- Session End compliance was 4%, enforced by trust alone.
- No validation step ran between an agent finishing work and closing the
  session, so nothing caught the gap.

## Why it still matters

The 79-versus-4 split is the sharpest local evidence that a handoff step with no
verifier is not performed. It explains why the orchestrator's handoff contract
names required fields instead of asking agents to remember them.

## Related

- [orchestration-003-orchestrator-first-routing](orchestration-003-orchestrator-first-routing.md)
- [orchestration-parallel-execution](orchestration-parallel-execution.md)
- [protocol-001-verificationbased-gates](../protocol/protocol-001-verificationbased-gates.md)
