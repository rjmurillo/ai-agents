<!-- placement: evidence; reason: a dated incident where a retroactive gate blocked an artifact created before the gate existed -->

# Protocol: A Gate Applied Retroactively Blocked PR #53

The session protocol, its validator prompt, and the grandfathering markers are
all gone (commit `ba541c21f`). The incident is kept because the failure shape
recurs whenever a new gate meets artifacts that predate it.

## Observation (2025-12-21, PR #53)

A session file dated 2025-12-20 blocked the merge of PR #53. It failed three
checks that did not exist when it was written:

- no Protocol Compliance section, because none was required yet;
- initialization evidence in the format used at the time, not the new one;
- handoff evidence from the older workflow.

Resolution: the file was annotated as predating the requirement, and the
validator passed.

## Transferable reading

A gate that reads existing artifacts needs an answer for the ones created
before it. Without one, the gate blocks work that has nothing to do with the
defect it was built to catch, and the cheapest route around it is to weaken the
gate for everyone.

## Related

- [protocol-001-verificationbased-gates](protocol-001-verificationbased-gates.md)
- [protocol-014-trust-antipattern](protocol-014-trust-antipattern.md)
