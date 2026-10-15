---
source: wiki/concepts/AI Safety/Agent Guardrails Template.md
created: 2026-06-01
review-by: 2026-09-01
---

# Agent Guardrails Template

## Principle

Constraints enable speed by eliminating self-checking overhead. Without
guardrails, agents waste tokens on safety verification per request. With
guardrails, agents know their boundaries and spend tokens on building. This is
the complement to `autonomous-execution-guardrails.md`: that reference covers
the pre-merge checklist, this one covers the constraint model an agent operates
under.

## The Four Laws Of Agent Safety

Asimov-style ordering, general to specific. Lower-numbered laws win in conflicts.

1. **Do not take actions outside the declared scope.** The agent's permissions
   are defined upfront. It refuses out-of-scope actions.
2. **Verify before destructive operations.** An explicit confirmation tier
   guards irreversible actions.
3. **Preserve the audit trail.** Every action is logged with its reasoning and
   tool calls.
4. **Escalate when uncertain.** Confidence-tier thresholds; below threshold,
   hand back to a human.

The asymmetry matters: do not claim "verified" if the action is outside scope;
do not act outside scope just because the audit trail is pristine.

## Why "Constraints Enable Speed"

Without explicit guardrails, agents self-check every action ("am I allowed to do
this?"), hedge in output, refuse marginal cases unnecessarily, and burn tokens
on safety verification per request.

With explicit guardrails, boundaries are known, in-scope actions are taken
without a hedge, out-of-scope actions are refused fast (one decision, not
per-token deliberation), the audit trail relieves the agent from re-explaining
each step, and the escalation path is the safety valve rather than constant
self-doubt.

## How To Apply

- Every skill or hook names its scope. Out-of-scope means an explicit refusal,
  not a best-effort attempt.
- A destructive operation (delete, force-push, schema drop, irreversible
  external call) maps to Law 2: it needs a confirmation tier.
- A new agent tool is audited against the Four Laws before it ships.

## Caveats

- The template is opinionated; not every guardrail applies to every project.
- Guardrails are necessary but not sufficient for substrate-tier safety.

## Why This Lens Applies In PR Review

When a diff adds or changes an agent prompt, a skill (`SKILL.md` or its
scripts), or a lifecycle hook, check it against the Four Laws. Does the change
declare its scope and refuse outside it (Law 1)? Does any new destructive or
irreversible action have a confirmation tier (Law 2)? Does the new path log its
reasoning and tool calls (Law 3)? Does it escalate to a human below a confidence
threshold instead of guessing (Law 4)? A change that widens what an agent can do
without adding the matching guardrail is the failure this concept guards
against. Flag the missing law by number.

## Connections

- Autonomous execution guardrails: the pre-merge checklist and "won't fix"
  protocol that Law 3 and Law 4 enforce at review time.
- Agent unauthorized memory inference: a concrete Law 1 violation (acting
  outside the granted scope on a memory write).

## Source

Open-source agent guardrails framework, 2026.
