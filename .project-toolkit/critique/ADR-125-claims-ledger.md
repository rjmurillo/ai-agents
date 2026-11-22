# ADR-125 claims ledger

Evidence date is 2026-11-21.
The original evidence run used base `2c9a48510df3425df469d35f87579ff1817dada6`.
The readiness evidence comes from `2c15cf91999a43a568c91a245f8817b2bd3cc741`.

| Claim | Evidence | Result |
| --- | --- | --- |
| Readiness has 131 coupling regressions. | Isolated verifier replay on readiness with the base and head pinned. | 131 coupling, three cohesion, and two encapsulation regressions. |
| The raw readiness assessment still fails. | Unchanged `check_regression` and `adapt_local_axis_verdict`. | Raw exit 10 maps to FAIL. |
| The main ruleset does not require owner review. | GitHub branch rules endpoint for `main`. | Zero required approvals and code-owner review disabled. |
| The canonical API identifies the owner. | GitHub issue comment 6995934831 on issue #7436. | Login `rjmurillo` and association `OWNER`. |
| A valid owner approval retains raw scores and reports WARN. | The verifier's real-assessor fixture substitutes the API response. | WARN includes the pinned base and head, comment, digest, and reported regressions. |
| Incorrect owner, issue, digest, or edited comment cannot approve. | The verifier tests replace these fields separately. | Each denial returns exit 1. |
| Sparse and index-hidden files cannot change the candidate assessment. | The verifier's two checkout isolation tests. | The committed inventory remains identical. |
| Absolute failures stay blocking. | The absolute threshold test adds a duplicated source file beside a comparable regression. | The verifier returns 1 even when the assessor exits 10. |
| Candidate scanner and config changes cannot qualify. | Two verifier tests modify each trusted input separately. | The verifier returns 1 before assessment. |

The procedure, verifier, and decision use one trusted assessment.
The owner hash covers the exact base, head, and reported regressions.
The ordinary marker continues to attest to the verdict of its review.

The readiness approval digest is `7a213ba45cf123571e97abb349df806ea9f633a2c0e8c3d53a8aff6102761943`.
Run the verifier with both pinned commits and an absolute assessment output path.
