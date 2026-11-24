---
id: ADR-125
status: accepted
date: 2026-11-24
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

## Amendment 2026-11-24

### Why

Issue #7525 reports that the approval loop costs more than it protects.
The owner reports three re-pins on tracking issue #7528 for one consolidation branch.
The Consequences section says to revisit if unrelated main changes repeatedly force new approvals.
The #7528 re-pins came from main moving and from the branch's own fix commits.

The frontmatter consolidation branch was assessed at `0a101a596` against `a217e3a3d1` on 2026-11-24.
It produced 74 regression rows.
72 were coupling rows. 70 added an import of the shared `hook_utilities` parser.
The other 2 added an import of a helper made in the same branch.
One non-redundancy row came from a test file that lost 131 code lines.
Its duplicated lines fell from 56 to 33, yet the ratio score fell 7.3 to 6.0.

### Change

The first decision kept three things fixed that this amendment changes: exit behavior, a new optional config key, and a new JSON field.
Scores and raw regression rows stay as before.

1. The assessor admits a non-redundancy drop when no line gained a copy.
   Each line's repeat count at head must not exceed its count at base.
   This admission is on for every consumer and language.
2. The assessor admits a Python coupling drop when third-party import roots did not grow.
   This admission is off unless the config sets `firstPartyCouplingAdmission`.
3. A root is first-party only when the HEAD commit holds `<root>.py` or `<root>/__init__.py`.
   The search covers the file's folder, its parents in the workspace, and each `importRoots` entry.
   A root the scanner's interpreter loads from site-packages is always third-party.
   A same-named folder cannot hide a dependency the scanner has installed.
   A dependency missing from the scanner's environment can be shadowed by a tracked package in the diff.
4. Each admitted row's record is stored under `change_admissions` in the comparison.
5. The review adapter reports an admitted row as WARN.
6. A run with only admitted rows exits 0, so no owner comment applies.
7. Other regressions still exit 10 and still need this ADR's approval path.
   These include new third-party roots, new duplicate copies, and other qualities.

The repository config sets `importRoots` to `src/claude/lib`.
On the consolidation branch, 69 of 74 rows are admitted.
Four remaining rows add a direct `yaml` import.
One remaining row is a cohesion drop of 0.9 from file growth.
That branch still needs one owner approval, or code changes, for those rows.

### Relation to ADR-122

ADR-122 rejected a generic exception framework with no present need.
Issue #7525 is that need. It reports three approval rounds on #7512; the owner reports three re-pins on #7528.
ADR-122 records name one file and one score transition, authorized by a person.
These admissions are rules instead; they hold for any file whose change meets them.
The adapter checks each record's own numbers against its rule.
For non-redundancy it sees only totals; the assessor enforces the per-line rule.

### Alternatives

| Alternative | Consequence |
| --- | --- |
| List shared packages in config | Three rows stay: two import a branch-local helper, one adds `yaml`. |
| Raise the regression tolerance | Rejected above; unrelated drops would pass. |
| Count distinct modules, not statements | Clears 1 of 72 coupling rows and changes every score. |
| Stop gating coupling | Loses the signal for a new third-party dependency. |
| Drop first-party imports from the score | Conflicts with first-party Go scoring from PR #7051 (issue #7047). |
| Make the non-redundancy admission opt-in | Every consumer keeps a gate that punishes deleting unique lines. |
| Fix the non-redundancy ratio score | Changes every score and every absolute verdict, not only regressions. |
| Bind approval to rows, not commits | Keeps an owner comment per branch; tracked in issue #7525. |

### Consequences

A shared-helper extraction no longer needs an owner comment.
A file that adds many new first-party imports passes as WARN.
Reviewers see that WARN in the report, but nothing blocks it.
More imports from a third-party root the file already uses also pass as WARN.
A namespace root such as `google` counts once, so a new subpackage under it passes.
A Python file swapping one third-party package for another still blocks.
Coupling admissions cover Python only; other languages keep the old behavior.
Consumers keep the old coupling behavior until they opt in.
The non-redundancy admission applies to every consumer with no opt-out.
A non-redundancy drop of any size passes when no line gained a copy.
Ordinary runs read the branch's own config, so an `importRoots` edit needs review.
The approval verifier reads the config from the integration commit instead.
Base imports resolve against the head tree, so a renamed file can misjudge a base import.
Removing `firstPartyCouplingAdmission` reverses the coupling rule.
Reversing the non-redundancy rule takes a code change.
Coupling is opt-in because first-party imports are real coupling; that trade is a repository choice.
Non-redundancy is on for all because a file that adds no copy of any line cannot have gained duplication.
A shipped plugin file that adds an upstream-only first-party import is admitted; no gate parses those imports yet.
Revisit these rules if an admitted row hides a dependency a reviewer later rejects.
The reviewer records each such case as a comment on issue #7525.
The evidence base is one branch; other branches were not replayed.
