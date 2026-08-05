# ADR Debate Log: ADR-043 Correction Note

## Summary

- **ADR**: `.agents/architecture/ADR-043-scoped-tool-execution.md`
- **Change**: Appended correction note to Implementation Notes section
- **Issue**: #4401
- **Date**: 2026-08-03
- **Rounds**: 1 (Triage + verification)
- **Outcome**: APPROVED

---

## Context

Issue #4401 reported that ADR-043 line 60 claims `--no-globs` ensures "only
specified files are processed". This is mechanically wrong: the flag governs
the config's `globs` key only (which adds paths). It says nothing about
`ignores`. The issue traced the harm: a reviewing agent cited the ADR note as
evidence that dropping `--no-globs` from the wrapper was a downgrade.

## adr-review Protocol

### Analyst Review

**Finding**: The claim is not merely stale, it is an assertion about tool
mechanics that was never true in the reading it invites. The issue text
correctly distinguishes this from the case where an ADR names a superseded
command (historical record, leave alone).

Verified against `.markdownlint-cli2.yaml` lines 90 to 97: the `globs` key was
removed deliberately, and the comment at that location documents that `ignores`
stays active for explicit walks. That is the direct contradiction of "only
specified files are processed."

### Architect Review

The original Decision ("MUST scope to changed files") is correct and should be
preserved. The correction is scoped to an appended note, not an in-place edit of
the Decision or Implementation Notes. This preserves the historical record the
ADR carries while correcting the mechanical claim.

Accepted on the grounds that a stale claim and a mechanically wrong claim are
different objects. The note format follows the precedent set by other
ADRs that have accumulated correction notes.

### Independent-Thinker Review

Two alternative interpretations were considered:

1. Leave ADR untouched; correct only the agent that misread it. Rejected:
   ADR-043 is the authority the SESSION-PROTOCOL.md change cites. A reader who
   follows the citation finds the wrong mechanics. Correcting only downstream
   consumers leaves the source wrong.

2. Edit the original Note in place. Rejected: the architect's position that
   historical records should not be churned was accepted. The appended
   correction meets both requirements.

## Verdict

APPROVED. Append correction note only. Do not edit the original Decision or
Implementation Notes. Add a regression test so the wrong phrase cannot
re-enter any ADR or rule file.

## Evidence

- Verified ADR-043 line 60 text: "ensuring only specified files are processed"
- Verified `.markdownlint-cli2.yaml` lines 90 to 97: globs removed, ignores retained
- Verified `uv run --frozen python scripts/validation/pre_pr.py --markdown-lint-only`
  as the current entry point (reports files actually read)
- Regression test: `tests/test_adr_043_no_globs_scope.py` (7 tests, all pass)
- Mutation check: 3 mutations each killed relevant tests; cosmetic mutation survived
