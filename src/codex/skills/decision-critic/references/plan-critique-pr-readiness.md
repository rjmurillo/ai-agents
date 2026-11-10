# Pre-PR Readiness Validation

Loaded by the `critic` agent when it is asked to validate PR readiness.

When asked to validate PR readiness, check against this list:

- [ ] All acceptance criteria have test evidence
- [ ] No BLOCKING verdicts unresolved
- [ ] Commit count is reasonable for the change (advisory only; no hard cap)
- [ ] Any staged or supplied session log validates
- [ ] Atomic commits (one logical change each)
- [ ] No secrets, absolute paths, or internal refs in src/
