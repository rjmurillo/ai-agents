# Issue #3399 ADR prose hook reference debate log

## Scope

ADR Review Protocol evidence for ADR-033, ADR-061, ADR-062, ADR-081, ADR-082, ADR-084, and ADR-085.

## Finding

The staged ADR edits are factual corrections only. They do not change any ADR decision, status, alternative, or consequence. They either point prose at the current enforcement surface, such as the lefthook `adr-review-policy` and `retrospective-policy` jobs, or mark deleted hook references as historical with nearby retirement wording.

## Review

- architect: Accept. The edits preserve decision intent and remove stale implementation pointers.
- planner: Accept. The work is bounded to issue #3399 and does not create new migration scope.
- qa: Accept. The new test fails against unmarked stale prose and passes after the factual corrections.

## Decision

Accept these ADR prose corrections as non-substantive factual maintenance for issue #3399.
