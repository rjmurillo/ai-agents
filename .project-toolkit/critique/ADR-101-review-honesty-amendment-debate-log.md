# Debate Log: ADR-101 review-honesty amendment

**Records**: ADR-101
**Trigger**: The repository owner directed on 2026-11-01 that review claims in
this repository be stated honestly: the agent panel is one vote, and a checked
review box needs a linked artifact.

## No debate was held

Recording that plainly rather than manufacturing one. No agent panel and no
reviewers were convened. This amendment states a property the record already
relied on and adds no mechanism, so there is nothing for six roles to disagree
about. It also adds no AI reviewer and no AI check, which the owner ruled out.

## Governing evidence

Owner Direction, 2026-11-01: change the security review checkboxes in the pull
request template to require a run URL or file path, and add to ADR-101 that the
six-role panel counts as one vote because every role shares one model family,
and that review assurance equals the required deterministic contexts plus
post-merge detection.

The context count was checked against the source rather than taken from the
direction. `scripts/ci/ruleset_required_contexts.py` pins nine contexts at
`origin/main` commit `7d6af226f`. ADR-101 still cites eight in its Context section,
impact table and Phase 1, so the amendment names nine and keeps the older
figure as history.

## What changed

1. `.github/PULL_REQUEST_TEMPLATE.md`: the two "Security agent reviewed" boxes
   now carry an `Artifact:` slot for a run URL or file path.
2. `ADR-101-enforcement-planes.md`: one amendment paragraph in the Status
   section. No other text in the record was edited, and the frontmatter is
   unchanged.

3. `ADR-101-enforcement-planes.md`: one doubled blank line between two list
   items was removed. It is whitespace only and renders the same. The amendment
   would otherwise push the record to 501 lines and regress the 500 line taste
   ceiling, and an ignore header cannot go above the frontmatter.

4. `ADR-101-enforcement-planes.md`: the last sentence of the amendment was
   reworded after a bot-assisted review on the pull request found it misplaced
   the eight contexts. The eight is cited from the required-contexts script in
   the Context section, the impact table and Phase 1, so the sentence now says
   the nine supersedes those figures and that they stay as the historical
   measurement.

## Position

Owner direction: accepted as the decision for this amendment.
