# ADR-125 debate log

Claims ledger: [ADR-125 claims ledger](ADR-125-claims-ledger.md).

## Round 1

The first design stored an approval file on the integration branch.
The architect and security seats voted Block on separate grounds.

| Seat | Finding | Resolution |
| --- | --- | --- |
| Architect | The raw assessment and the verifier could use different bases or interpreters. | The approval path uses one trusted assessment with both commits pinned. |
| Security | A sparse checkout or index flag could hide files from the assessor. | The verifier scans an isolated checkout of the committed head. |
| Security | Candidate code could run before the approval path. | The review procedure uses the trusted verifier for an approval-aware assessment. |
| Both | A prior marker remains usable after an approval disappears. | The ADR distinguishes fresh approvals from historical marker attestations. |

The live main ruleset requires zero approvals and disables code-owner review.
The revised design verifies an explicit owner comment on the tracking issue.
The first round did not reach consensus.

## Round 2

The second design sourced approval from a verified owner comment.
The architect, critic, and security seats voted Block.

| Finding | Resolution |
| --- | --- |
| The ordinary adapter could replace a verified WARN with FAIL or UNKNOWN. | Review extraction and marker instructions now carry the verifier's WARN. |
| Review scope could move before the approval scan or marker write. | Review pins both commits before evidence collection and rechecks before marking. |
| A missing or nonregular source could hide evidence. | The verifier checks changed paths and file modes before assessment. |
| Go scoring could use module context from outside the snapshot. | The verifier rejects external module context before assessment. |
| Python startup and the remote were insufficiently constrained. | The procedure verifies the canonical origin and runs both scripts in isolated mode. |

Raw exits 10 and 11 retain FAIL when approval verification fails.
The second round did not reach consensus.

## Round 3

The architect voted Disagree and Commit.
The critic, security, analyst, independent-thinker, and advisor seats voted Block.
The review focused on execution scope, evidence retention, and startup order.

| Finding | Resolution |
| --- | --- |
| A mixed-case Go suffix could bypass the module-context check. | The verifier normalizes the suffix, with a regression test for uppercase Go. |
| Review helpers still refer to mutable checkout state. | The procedure pins the diff and runs checkout-dependent helpers in a disposable checkout. |
| The marker recipe did not place the receipt. | The recipe includes the receipt outside the hashed report and links raw evidence. |
| A tracking issue needs the rationale for every accepted row. | The procedure records the inventory and evidence before requesting owner approval. |
| The first approval requires a deployed verifier. | The procedure lands the verifier first and then collects the new pinned inventory. |

The third round did not reach consensus.

## Round 4

The critic, security, analyst, independent-thinker, and advisor seats voted Accept.
The architect voted Disagree and Commit.
The architect reproduced the receipt's trailer separator defect.
The marker recipe now requires a blank line before the trailers.
The panel reached consensus without an open blocking vote.
