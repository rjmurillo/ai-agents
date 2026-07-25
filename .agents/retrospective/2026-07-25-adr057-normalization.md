# Retrospective: ADR-057 Workflow Reference Normalization (2026-07-25)

## Context

A Copilot PR reviewer flagged a consistency nit on PR 3315: the workflow file
`slash-command-quality.yml` was referenced by bare filename in three places in
ADR-057 and by full path in a fourth. The user directed that the fix be done
properly in a branch and opened as its own PR, stacked on PR 3315.

## What went well

- The actual change was a clean three-line copy-edit with zero semantic content.
  Verified against source: four references, all now full-path, zero bare, zero
  dashes.
- The adr-review was run for real (architect and critic sub-agents), not
  fabricated, and its factual claims (path exists, reference count, no table
  breakage) were re-verified directly against the working tree before recording
  consensus.

## What to improve

- A three-line documentation copy-edit triggered the full ADR governance chain:
  an adr-review debate log, a session log, and a retrospective, all required to
  pass the pre-commit and pre-push gates. The ceremony-to-change ratio here is
  high. This was disclosed to the user up front and accepted, but it is worth
  noting that the gates do not distinguish a semantic ADR decision from a
  reference-format normalization.

## Learnings captured

- The ADR-review pre-commit gate keys on the presence of a `*debate*.md` file
  referencing the ADR ID plus an adr-review pattern string in today's session
  log. It does not verify how many agents ran, so honesty about panel scope has
  to be self-enforced in the debate log itself.
- The retrospective pre-push gate is defeated by staging a `.json` session log
  (not documentation-only), so a session that edits only an ADR still needs a
  dated retrospective artifact to push.
- For a change with no semantic surface, a proportionate two-lens panel
  (architect, critic) with the omitted lenses recorded and justified is more
  honest than convening six agents to produce four empty verdicts.
