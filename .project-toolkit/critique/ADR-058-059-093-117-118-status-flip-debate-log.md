# Debate Log: proposed to accepted for five shipped ADRs

**Records**: ADR-058, ADR-059, ADR-093, ADR-117, ADR-118
**Trigger**: The repository owner directed on 2026-11-01 that ADRs which are
`implemented: true` must not stay `proposed`, and approved fixing all sixteen
such records. These five are the ones that can move with a status-only edit.

## No debate was held

Recording that plainly rather than manufacturing one. No agent panel and no
reviewers were convened. This is the owner carrying out a decision about the
lifecycle vocabulary, not a new architectural decision, so there is nothing for
six roles to disagree about.

## Governing evidence

Owner Direction, 2026-11-01: fix all identified ADR status drift, where
`status: proposed` sits beside `implemented: true`. That direction is the
approval ADR-073 asks for. `accepted` is not self-asserted here: the
authority is the owner's message, and this log is its record.

## What changed

1. The `status` field in the frontmatter of the five records above moved from
   `proposed` to `accepted`. No prose in any record was edited.
2. `check_adr_lifecycle.py` gained the `implemented-implies-decided` check, so a
   record that is shipped and still `proposed` now fails the gate.

## Why only five of sixteen

The sixteen were each flipped in a trial run. Eleven of them regressed an
existing ratchet because `accepted` activates checks that `proposed` skips:

- `prose-frontmatter-agree` requires the `## Status` prose to open with the
  frontmatter value. Seven records still open with `Proposed`.
- `cited-paths-exist` applies to accepted records only. Seven records cite
  paths that no longer exist.

Both ratchet baselines may only shrink, and fixing either needs a prose or
citation edit that the owner's direction for this change excluded. Those eleven
(ADR-038, 049, 067, 070, 075, 077, 078, 089, 098, 112, 119) are listed in the
new check's baseline and must leave it when their prose is repaired.

## Position

Owner direction: accepted as the decision for these five records.
