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

## Amendment 2026-11-24 claims

Evidence date is 2026-11-24.
The branch evidence uses base `a217e3a3d1f870b7477b20cfa4c5391e6041fab2` and head `0a101a596e0df8754b1bc38962079d26c3de50ac`.
The raw run lives outside the repository at `sessions/sol-loop-7469/cq6/inventory.json`.

| Claim | Kind | Command | Result |
| --- | --- | --- | --- |
| The branch produced 74 regression rows, 72 of them coupling. | count | Count `regressions` in the cq6 inventory by quality. | VERIFIED: 72 coupling, 1 cohesion, 1 non-redundancy. |
| Each coupling row added a first-party helper import. | behavior | AST diff of imported modules at base and head for each row. | VERIFIED: 70 rows added a `hook_utilities` module; 2 added a branch-local helper (`frontmatter_key_drop`, `citation_exemptions`). |
| The test file lost 131 code lines; duplicates fell 56 to 33. | count | Non-blank lines without `#` comments, and `_score_non_redundancy` reasons at both revisions. | VERIFIED: 131 fewer code lines; compared lines 208 to 82; unique 152/208 at base, 49/82 at head; the fixed run records `baseDuplicateLines` 56, `headDuplicateLines` 33. |
| A config list of shared packages leaves three rows. | count | Replay with `hook_utilities` roots excluded. | VERIFIED: `agent_capabilities.py`, `test_check_citation_freshness.py`, `test_instruction_budget.py`. |
| Distinct-module counting clears 1 of 72 coupling rows. | count | Replay counting distinct scored modules. | VERIFIED: 71 rows remain. |
| The fixed assessor admits 69 of 74 rows. | count | Fixed `assess.py` (SHA-256 `cbafef8e...7a50`) and `.qualityrc.json` (`fc710eeb...b9`), run with `-I` in a disposable clone at head; output in `sessions/cq-fix-7525/fixed2.json`. | VERIFIED: exit 10, 69 admitted, after the round 1 hardening. |
| Four remaining rows add a direct `yaml` import. | behavior | `_python_third_party_roots` at both revisions. | VERIFIED: `check_adr_exception_markers.py`, `doc_date_adr.py`, `validate_design_review.py`, `test_instruction_budget.py`. |
| The remaining cohesion row drops 0.9 from growth. | behavior | Inventory row and diff stat. | VERIFIED: 6.1 to 5.2, file gained 36 code lines. |
| Go scoring counts first-party packages as coupling. | quote | `_go_module_path` docstring in `assess.py`; `git log -S` on that text. | VERIFIED: "The module's own packages are application coupling", added by `86298335f6` (PR #7051, fixing issue #7047). |
| Tracking issue #7528 needed three re-pins. | behavior | Issue #7525 problem statement and the task record. | INFERRED from the owner report; not re-counted from issue history. |
| A decoy folder cannot admit an installed package. | behavior | `test_checkout_decoy_cannot_hide_an_installed_package` with the installed-package check removed. | VERIFIED: the test fails without the check and passes with it. |
| Untracked or bare folders are not first-party. | behavior | Two tests, with the index check replaced by a disk check. | VERIFIED: three tests fail under the disk check. |

