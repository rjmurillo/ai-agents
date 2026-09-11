---
type: task
id: TASK-026
title: Implement ADR-100 items 2-4 (advisory demotion)
status: todo
priority: P1
complexity: M
estimate: 4h
related:
  - DESIGN-022
created: 2026-09-11
updated: 2026-09-11
author: spec-generator
tags:
  - control-plane
  - adr-100
---

# TASK-026: Implement ADR-100 items 2-4 (advisory demotion)

## Objective

Deliver ADR-100 items 2, 3, and 4 in one combined change, satisfying
REQ-023's eight acceptance criteria.

## In/Out of Scope

In scope: `check_atomic_commit` rule-text and any remaining validator
blocking surface (item 2); `detect_scope_explosion.py`'s block-to-advisory
change and `_partition_generated` extension (item 3); `SKIP_SCOPE_CHECK`
removal (item 4), landed with or after item 3 in the same PR.

Out of scope: ADR-100 item 5 (`post_qa_code_changes`); item 1 (already
delivered, verify only, do not re-touch).

## Acceptance Criteria

- [ ] TASK-026-AC1: Resolve REQ-023 OQ1 (remaining `check_atomic_commit`
      blocking surface) and OQ2 (the "four documents") before editing code.
- [ ] TASK-026-AC2: `.claude/rules/universal.md` MUST-6 reads as advisory.
- [ ] TASK-026-AC3: `detect_scope_explosion.py`'s `BLOCK_THRESHOLD` path
      reports, does not exit nonzero for the threshold reason.
- [ ] TASK-026-AC4: `_partition_generated` excludes
      `.agents/sessions/**`, `.agents/qa/**`, `.agents/memory/episodes/**`.
- [ ] TASK-026-AC5: `SKIP_SCOPE_CHECK` handling removed, in the same commit
      as AC3/AC4.
- [ ] TASK-026-AC6: `uv run pytest tests/validation/test_always_on_corpus_claims.py
      tests/validation/test_audit_procedure_claims.py -q` passes with
      advisory-updated expectations.
- [ ] TASK-026-AC7: ADR-100 item 1's already-delivered status verified
      unchanged (`git_hook_policy.py:6727`,
      `scripts/ci/enforce_pr_validation.py`).
- [ ] TASK-026-AC8: `uv run python scripts/validation/pre_pr.py` passes.

## Files Affected

| File | Action | Description |
|---|---|---|
| `.claude/rules/universal.md` | modify | MUST-6 reduced to advisory text |
| `scripts/detect_scope_explosion.py` | modify | report-only above threshold; `_partition_generated` extended; `SKIP_SCOPE_CHECK` removed |
| `tests/validation/test_always_on_corpus_claims.py` | modify | advisory-updated expectations |
| `tests/validation/test_audit_procedure_claims.py` | modify | advisory-updated expectations |
| `scripts/detect_scope_explosion.py`'s own test module | modify | exit-0-with-report assertions; `SKIP_SCOPE_CHECK` removal assertion |
| (four documents per OQ2, resolved before edit) | modify | refreshed figures per ADR-100 item 2 |

## Implementation Notes

1. Read ADR-100 in full (not only lines 246-266) before touching any file,
   to resolve OQ2's "four documents" citation.
2. Verify `check_atomic_commit`'s current blocking status directly in
   source; ADR-100 item 1's own text already found both CI/pre-push
   commit-ceiling sites non-blocking, so item 2's remaining work is likely
   text-only, but confirm rather than assume.
3. Implement items 3 and 4 as one commit (or one PR with item 4's commit
   strictly after item 3's), never the reverse order.
4. Run the two named test files locally before push (fast, seconds-scale)
   per the original seed plan's R3 mitigation.

## Testing Requirements

`uv run pytest tests/validation -k "atomic_commit or scope_explosion or
always_on_corpus or audit_procedure" -q`, then `uv run python
scripts/validation/pre_pr.py`. No new test framework; extend existing
validator test modules with advisory-outcome assertions.
