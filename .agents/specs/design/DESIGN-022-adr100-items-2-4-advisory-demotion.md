---
type: design
id: DESIGN-022
title: ADR-100 items 2-4, demote scope and atomic-commit gates to advisory
status: draft
priority: P1
related:
  - REQ-023
adr: ADR-100
created: 2026-09-11
updated: 2026-09-11
author: spec-generator
tags:
  - control-plane
  - adr-100
---

# DESIGN-022: ADR-100 items 2-4, demote scope and atomic-commit gates to advisory

## Requirements Addressed

- REQ-023: ADR-100 items 2-4, demote scope and atomic-commit gates to advisory

## Design Overview

Three small, ordered edits against ADR-100's own text, no new components:

1. **Item 2**: confirm `check_atomic_commit`'s remaining blocking surface
   (OQ1), then reduce `.claude/rules/universal.md` MUST-6 to advisory
   language and refresh the documents
   `tests/validation/test_always_on_corpus_claims.py` cites.
2. **Item 3**: change `scripts/detect_scope_explosion.py`'s
   `BLOCK_THRESHOLD` return path from exit 1 to a report-only exit 0, and
   extend `_partition_generated`'s exclusion list with
   `.agents/sessions/**`, `.agents/qa/**`, `.agents/memory/episodes/**`.
3. **Item 4**: remove the `SKIP_SCOPE_CHECK` env-var honor at
   `scripts/detect_scope_explosion.py:492`, in the same commit as item 3
   (never before it).

## Component Architecture

No new components. Existing components touched:

```text
.claude/rules/universal.md          (MUST-6 text)
scripts/detect_scope_explosion.py   (BLOCK_THRESHOLD path, SKIP_SCOPE_CHECK)
scripts/validation/pre_pr_sequence.py (verify no gate-registration change needed)
lefthook.yml:395, :527              (verify invocation sites unaffected by
                                      the report-only exit-code change)
tests/validation/test_always_on_corpus_claims.py  (updated expectations)
tests/validation/test_audit_procedure_claims.py   (updated expectations)
```

## Technology Decisions

| Decision | Choice | O5 source | Rationale |
|---|---|---|---|
| Item 3/4 ordering | 4 lands with or after 3, never before | ADR-100 item 4's explicit text | Prevents a blocking-gate-with-no-relief window (REQ-023 AC-07) |
| Advisory signaling | Same report format the validators already print, minus the nonzero exit | ADR-100 items 2/3 text ("stays as advisory output", "reports only") | No new output format to design or test |
| No new advisory-gate framework | Demote each validator using its own existing code path | Abort-if clause 3, YAGNI | Two validators is not enough consumers to justify a shared abstraction |

## Decision-rule Traceability

| Decision rule | O5 source | Where enforced |
|---|---|---|
| Item ordering (4 after 3) | ADR-100 text, restated as this cohort's O5 in spirit | Single combined PR, verified by REQ-023 AC-07 |
| DR1 (measurement-only) is N/A here | ontology fragment | This REQ is not a measurement script; DR1 does not apply |

## Security Considerations

See REQ-023's Security section. This design removes a documented
self-attested-approval bypass (`SKIP_SCOPE_CHECK`) with a recorded abuse
history; no new mitigation is required because the change is a removal, not
an addition.

## Testing Strategy

- Update `tests/validation/test_always_on_corpus_claims.py` and
  `tests/validation/test_audit_procedure_claims.py` expectations from
  blocking to advisory (REQ-023 AC-06); run both locally before push
  (about one second, per the original seed plan's R3 mitigation).
- Update `scripts/detect_scope_explosion.py`'s own unit tests (wherever
  they live) to assert exit 0 with advisory output above
  `BLOCK_THRESHOLD`, and to assert `SKIP_SCOPE_CHECK` is no longer read.
- Confirm `pre_pr_sequence.py`'s gate wiring for both validators does not
  need a signature change; if the gate framework currently branches on the
  validator's exit code to decide pass/fail/advisory, verify that branch
  already supports an advisory outcome (it does for other advisory gates
  in `_SEQUENCE`, for example "Temp-filesystem Worktrees (advisory)").
- `uv run pytest tests/validation -k "atomic_commit or scope_explosion or
  always_on_corpus or audit_procedure" -q`, then the full
  `uv run python scripts/validation/pre_pr.py`.

## Open Questions

- OQ1 and OQ2 from REQ-023 (remaining blocking surface for item 2; the
  identity of "the four documents"); both resolved at TASK-026 time by
  reading the validator source and the full ADR-100 text before writing
  code, not guessed here.
