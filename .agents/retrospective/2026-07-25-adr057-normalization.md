# Retrospective: ADR-057 Workflow Reference Normalization (2026-07-25)

## Failure mode classification

Primary class: **6, Multi-agent rubber-stamping** (`.agents/governance/FAILURE-MODES.md`).
This session was a near miss, not an incident. The adr-review pre-commit gate
keys on the presence of a `*debate*.md` file naming the ADR ID plus an
adr-review pattern string in the day's session log. It does not check how many
lenses ran, whether each cited a file and line, or whether any dissent was
recorded. An honest two-lens panel and a fabricated six-agent panel pass the
gate identically. The panel here ran for real and its factual claims were
re-verified against the working tree, so the failure did not land, but the gate
provided none of that assurance.

Secondary class: **4, False completion markers**. The first commit's session log
recorded evidence strings claiming four files were staged when the commit hooks
had also regenerated the memory episode and `.agents/memory/causality/causal-graph.json`,
for six files total. The episode metrics recorded `commits: 0` while the session
log marked `changesCommitted` complete. Both were corrected in this PR after the
Copilot reviewer flagged them.

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

## Impact

| Area | Severity | Effect |
|------|----------|--------|
| ADR-057 content | Low | Reference format only. No semantic change. |
| Governance gate confidence | Medium | The adr-review gate cannot distinguish an honest panel from a rubber-stamped one. |
| Session-log accuracy | Medium | Evidence strings and episode metrics disagreed with the actual commit until corrected. |
| Ceremony cost | Low | A three-line copy-edit required four governance artifacts. |

## Evidence

- PR #3327 (this change): normalizes the three bare workflow references in ADR-057.
- PR #3315: where the Copilot reviewer raised the original consistency nit that was deferred.
- Commit `b2c8a534e7`: the six-file governance commit whose session log understated the staged set.
- Commit `622456fa97`: populated `endingCommit` and removed the contradictory `nextSteps` entries.
- Issue #3185: the ADR-057 eval-enforcement work this branch stacks under.
- `.agents/analysis/ADR-057-workflow-ref-normalization-debate.md`: the debate log recording the two-lens panel and the justification for each omitted lens.

## Remediation

| Action | Type | Owner or issue |
|--------|------|----------------|
| Correct the session-log evidence strings and episode metrics to match commit `b2c8a534e7` | Artifact fix | Done in PR #3327 |
| Add a `commit` event to the episode so `commits` and the event list agree | Artifact fix | Done in PR #3327 |
| Consider having the adr-review gate require a per-lens verdict block with at least one file and line citation, so panel scope is machine-checkable rather than self-enforced | Governance change | Refs #3185, needs its own issue before any gate edit |
| Consider a proportionality carve-out so a reference-format ADR edit does not require the full semantic-decision artifact set | Governance change | Refs #3185, needs its own issue before any gate edit |
