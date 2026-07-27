# Issue #3399 ADR prose hook reference debate log

> **Note**: This is an issue-level analysis note for #3399, not a formal ADR debate log (those reside in `.agents/critique/` per adr-review convention).

## Scope

ADR Review Protocol evidence for ADR-008, ADR-033, ADR-047, ADR-057, ADR-061, ADR-062, ADR-081, ADR-082, ADR-083, ADR-084, and ADR-085.

## Finding

The staged ADR edits are factual corrections only. They do not change any ADR decision, status, alternative, or consequence. They either point prose at the current enforcement surface, such as the lefthook `session-policy`, `adr-review-policy`, and `retrospective-policy` jobs, require a new or restored enforcement point where the old hook was removed, or mark deleted hook references as historical with same-context retirement wording.

Review r2 added two factual corrections. ADR-062 now states the #1993 per-turn reassertion hook was removed and no longer ships. ADR-083 no longer claims the removed `invoke_security_gate` and removed `invoke_security_commit_gate` hooks are present in the shipped base.

## Review

- architect: Accept. The edits preserve decision intent and remove stale implementation pointers.
- planner: Accept. The work is bounded to issue #3399 and does not create new migration scope.
- qa: Accept. The strengthened test fails against base ADR prose and passes after the factual corrections.

## Decision

Accept these ADR prose corrections as non-substantive factual maintenance for issue #3399.
