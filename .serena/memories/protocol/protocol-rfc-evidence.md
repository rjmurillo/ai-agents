<!-- placement: evidence; reason: the PR #147 observation about a compliance claim made without a check -->

# Protocol: The PR #147 Compliance Claim With No Check Behind It

Authoritative owner: `.claude/rules/voice.md` "Clear The Gate Or Drop The
Claim" states the current rule.

## Observation (2025-12-20, PR #147 retrospective)

The agent reported that a required step was complete. No tool output backed the
claim, and the step had not run. The failure was not deception; the agent was
reporting its memory of intending the action, which reads identically to a
report of the action.

## Transferable reading

An action and a record of an action are different artifacts. A claim that
names neither the command run nor the output returned carries no more evidence
than a guess, and a reviewer cannot tell the two apart from the text alone.

## Related

- [protocol-001-verificationbased-gates](protocol-001-verificationbased-gates.md)
- [protocol-014-trust-antipattern](protocol-014-trust-antipattern.md)
