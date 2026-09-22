<!-- placement: evidence; reason: a reuse observation for the blocking-gate pattern outside its original domain -->

# Protocol: The Blocking-Gate Pattern Transferred to ADR Review

Authoritative owner: `.claude/skills/adr-review/SKILL.md` describes the live
trigger. The mechanism has since moved to `detect_adr_changes.py`, so treat the
signal-and-detect description below as history.

## Observation (Session 92)

The gate pattern that held session-start compliance at 100% was reused for ADR
review, in a different domain:

1. The agent signalled the orchestrator with an explicit mandatory next step.
2. The orchestrator matched the signal.
3. The orchestrator blocked the workflow until the review completed.

Result: every ADR triggered a review. The files changed at the time were
`src/claude/architect.md`, `src/claude/orchestrator.md`, `AGENTS.md`, and
`.claude/skills/adr-review/SKILL.md`.

## What made it transfer

The pattern held because the signal was explicit, the detector existed, and the
consequence of skipping was defined. The counter-example from the same period:
skill documentation that described a mandatory step with no detector, which
changed nothing.

## Related

- [protocol-001-verificationbased-gates](protocol-001-verificationbased-gates.md)
- [protocol-014-trust-antipattern](protocol-014-trust-antipattern.md)
