---
id: ADR-125
status: accepted
date: 2026-11-21
decision-makers:
  - rjmurillo
supersedes: []
superseded-by: null
explainer: null
implemented: false
---

# ADR-125: Require Exact Approval of Code-Quality Review Findings

## Context

Issue #7512 records 131 coupling score drops in the readiness branch.
Issue #7512 attributes 103 one-point drops to three shared-helper changes.
The assessor counts imports, which can penalize moving repeated code into helpers.
The review adapter turns raw exit 10 into FAIL.
The ship workflow requires a SHA-bound review marker.

The maintainer selected a separate gate fix in readiness decision D30.
Each decision to accept score drops still needs an evidence review.
The live main ruleset requires zero approvals and disables code-owner review.
A merged approval file alone therefore gives no evidence of owner approval.

## Prior Art Investigation

ADR-122 admits three parser changes with fixed in-code records.
It preserves raw evidence and reports admitted regressions as WARN.
Those records apply to parser changes and retain their existing behavior.
The readiness branch needs a scoped decision across files and qualities.

## Decision

1. Keep the assessor's scores, output, configuration, and exit behavior.
2. Run the approval verifier from the pinned integration commit.
3. Use its trusted assessor and configuration in an isolated candidate checkout.
4. Preserve that single raw assessment as evidence for the review.
5. Bind owner approval to both commits and the reported comparable regressions.
   The assessor compares scores against their merge base.
6. Verify an unedited GitHub issue comment from the ai-agents repository owner.
7. Reject mismatches, evidence loss, absolute failures, and changed assessment inputs.
   Reject nonregular diff entries and Go module context outside the snapshot.
8. Report exact approvals as WARN and retain the raw FAIL for audit.
9. Keep ordinary warning acknowledgement and SHA-bound review proof.

The GitHub comment locator supplies the issue and comment IDs.
The verifier reads the comment's owner and body from the canonical repository.
The review marker continues to attest to the verdict of the reviewed commit.
Other review axes continue to gate independently.

## Alternatives

| Alternative | Consequence |
| --- | --- |
| Leave the release blocked | Preserves the gate while delaying the reviewed refactors. |
| Increase the regression tolerance | Unrelated changes could pass with lower scores. |
| Embed readiness transitions in the assessor | Every new change would need another scorer patch. |
| Trust a merged approval file | The current ruleset does not require owner approval. |
| Verify an explicit owner comment | A precise owner decision remains visible in the tracking issue. |

## Consequences

Land the verifier on main before requesting an approval for readiness.
Require evidence for each row in the tracking issue.
The review output and marker link that evidence.
A maintainer can accept the measured regressions without changing scoring.
Fresh reviews on different commits need a new owner decision.
Verification needs Git, the trusted parser environment, and the public GitHub API.
Deleting or editing the comment prevents approval on fresh reviews.
Existing markers remain attestations of their original review.
The ordinary marker reader accepts eligible clean merges above those markers.
Revisit this policy if unrelated main changes repeatedly force new approvals.
Removing the verifier and review procedure reverses this decision.
