---
id: ADR-113
status: accepted
date: 2026-09-30
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: false
review-by: 2027-03-31
---

# ADR-113: Promotion Gate Evidence, Artifact Binding, and Governed Exceptions

## Context

Epic #5636 closes paths where a check turns green without proving its contract. Its last block asks for a promotion gate. The epic lists five requirements, quoted verbatim:

- "Promotion aggregates applicable analysis and validation results."
- "Every result binds to the exact candidate artifact."
- "Exceptions record rationale, owner, approval, expiry, and remediation date."
- "Expired exceptions fail closed or block promotion."
- "Reports distinguish remediated, accepted, expired, and unresolved findings."

Today no such gate exists. The only release workflow is `.github/workflows/publish.yml`, which publishes to npm on a `v*` tag push or on a manual dispatch with `dry-run` set to false. Its `validate` job checks package metadata, tag-to-version match, and pack size. Nothing in it reads the results of the repository's test, analysis, or validation checks for the tagged commit. A repository search for "promotion gate" finds only the skillbook tier logic, which is unrelated.

The pieces are partly built. `scripts/validation/evidence.py` defines five states (`PASS`, `FAIL`, `SKIP`, `BLOCKED`, `UNKNOWN`), a `revision` field on every result, worst-wins aggregation, and `PolicyException`. That exception type carries a validator, states, reasons, a justification, and a reference. It has no owner, approval, expiry, or remediation date, so it cannot meet the third and fourth requirements.

ADR-101 sets the constraint on where the verdict is computed: "A gate protecting artifacts at plane N must compute its verdict at a plane above N, from evidence the gated actor cannot forge." A promotion gate that reads results the candidate itself wrote would repeat the failure ADR-101 records.

The decision is needed now because the typed-state work (#5635, #5636) already emits the results a gate would aggregate. Without a decision on binding and exceptions, each new consumer would invent its own.

## Decision

1. **One aggregator, one manifest.** A checked-in Python program computes the promotion verdict. It reads typed results, applies worst-wins aggregation through the existing `aggregate` function, and writes one JSON manifest. Workflow YAML only calls it. Both routes to `npm publish` in `publish.yml` (a `v*` tag push and a `workflow_dispatch` with `dry-run` set to false) pass through it.
2. **Results are persisted, and the store is named.** Each job that runs a validator uploads its `CheckOutcome.to_dict()` output as a JSON evidence artifact. The aggregator also reads the job's check-run conclusion for the candidate SHA through the GitHub API. Today typed results are printed lines only, so the upload is new work. A result with no bound evidence artifact is missing, even when a green check-run exists. The check-run corroborates an artifact and cannot stand in for one: a check-run with no `CheckOutcome` is `UNKNOWN`. An artifact is tied to its check-run by workflow run id and job name, both read from the API, so a green job A cannot corroborate an artifact from job B. A check-run conclusion maps to a typed state: `success` corroborates; `failure`, `timed_out`, and `action_required` read as `FAIL`; `neutral`, `skipped`, `cancelled`, `queued`, `in_progress`, and an absent check-run read as `UNKNOWN`. A matrix job corroborates only when every one of its check-runs is `success`. The result is the worse of the artifact's state and the check-run's.
3. **Applicable results are computed, not listed by hand.** A checked-in applicability table maps candidate contents (for example, "contains a workflow file") to the validators that must have run. A missing applicable result is `UNKNOWN`, never `PASS`. An empty result set is `UNKNOWN`, as `aggregate` already does for empty child sets. The applicability table has the same CODEOWNERS protection as the exceptions file. Gate coverage equals table coverage: a required check the table does not list is never consulted, so a drift check compares the required-checks ruleset with the table.
4. **Every result binds to the candidate, in two tiers.** The candidate is a commit SHA plus the SHA-256 digest of the npm tarball. Results computed before the build (tests, validators, analysis) bind to the SHA: the result's `revision` must equal the candidate SHA. Results about the build itself (pack size, package metadata, install smoke) bind to the SHA and the digest. The tarball is built once, in a single job, before the gate runs. The publish job downloads that exact file, recomputes its digest, and compares it with the manifest immediately before `npm publish`, so nothing can change between the check and the publish. This needs new code: `CheckOutcome` has no digest field today, and `aggregate` compares no revisions. A result bound to another SHA or digest is rejected and counted as missing.
5. **The verdict comes from a plane the candidate cannot edit, and the trust root is named.** The gate step runs from a workflow definition on the default branch, not from the tagged commit's copy of `publish.yml`, because a tag push executes the workflow file at the tagged commit and the candidate could edit the call. The publish entry point is a default-branch workflow that takes the candidate SHA as input. It rejects a SHA that is not an ancestor of the default branch head or does not match the tag. Creation of `v*` tags is restricted by a tag ruleset. The candidate is therefore a merged default-branch commit, and its results are the `push` and `merge_group` runs for that SHA. Those runs use the candidate's own workflow files, so their trust rests on required review of workflow edits (ADR-101), and the manifest states that limit. The aggregator verifies every result through the workflow-run API, never from the artifact body: the run's event, workflow path, ref, and `head_sha` must match, and a check-run must come from the GitHub Actions app with its `integration_id` pinned, because a same-named check-run from another writer is otherwise indistinguishable. This pin is weaker than the separate publishing App that ADR-101 Phase 0 calls for: head-defined runs and base runs are both the Actions app. An artifact is accepted only when its workflow run id passes those checks. The aggregator never deserializes an artifact from a run that fails them, per ADR-101. The exceptions file and the applicability table are read from the default branch. Residual: until the default-branch entry point, the integration pin, and the tag ruleset exist, the gate is advisory, and the manifest says so.
6. **Exceptions are governed records keyed to a finding.** A finding is identified by a fingerprint of validator, reason code, scope, and the item that failed (for example a file path). An exception names one fingerprint, not a whole validator and reason pair. `CheckOutcome` carries only a finding count and free-text detail today, so the fingerprint needs a new structured `items` field listing what failed. Until that field exists, an exception can key only on validator, reason, and scope, and per-item exceptions wait. Required fields: rationale, owner, approval, expiry date, remediation date. Approval is not a free-text name. It is an approving review by a CODEOWNER other than the author of the change that adds the record, read through the API at promotion time, with the reviewer recorded in the manifest. The exceptions file is CODEOWNERS protected.
7. **Single-owner interim rule.** The repository has one CODEOWNER. Until a second approving identity exists, no exception can be approved, so the gate accepts no exceptions and every unfixed finding is `unresolved`. This is deliberate: an exception a solo maintainer can approve for themselves is not governance.
8. **Expired or malformed exceptions fail closed.** Expiry is compared with the current UTC date at aggregator run time. A missing or unparseable date fails closed. An exception past its expiry licenses nothing, and the finding becomes `expired`. A record with a missing field, or a still-open finding past its remediation date, is rejected. A malformed exceptions file fails the load, which blocks every promotion until it is fixed.
9. **A finding is a non-pass typed state.** The mapping is fixed:

   | Typed state | Finding? |
   |---|---|
   | `PASS` | No |
   | `SKIP` with reason `policy.exempt`, or a validator the applicability table marks not applicable | No |
   | `SKIP` with any other reason | Yes |
   | `FAIL`, `BLOCKED`, `UNKNOWN` | Yes |
   | An applicable validator with no result | Yes, as `UNKNOWN` |

   Advisory licences in the pre-PR policy do not remove a finding here. They only stop a local push from blocking.

   The report names four classes. Each finding is exactly one of:
   - `remediated`: the finding appears in the previous promoted manifest and no longer reproduces at the candidate. The manifest links the fixing change.
   - `accepted`: an unexpired, approved exception covers its fingerprint.
   - `expired`: an exception covered it and has lapsed.
   - `unresolved`: no fix and no exception.

   The baseline for `remediated` is the previous promoted manifest, kept as a release asset. It affects only this non-blocking class. The first promotion has no baseline, so it reports no `remediated` findings. Promotion proceeds only when `unresolved` and `expired` are both zero. The manifest lists every finding by class. With decision 7, the first enforced promotion waits until the tree has no open finding, or until a second approver exists to accept them.
10. **Implementation is out of scope for this record.** This ADR fixes the contract. Building it is separate work under #5636 after the record is accepted, and the three parts (result binding, plane and trust root, exception governance) may be split into their own reviewed changes.

## Resolved Questions

Owner: rjmurillo. Decision D21, recorded in an [issue comment on #5636](https://github.com/rjmurillo/ai-agents/issues/5636#issuecomment-5924816280), accepted this record with solo-maintainer defaults for the three questions the proposal left open.

1. **Second approving identity.** None exists. Under decision 7 the gate accepts no exceptions for now, and every unfixed finding is `unresolved`. Adding a second approving identity re-opens decision 7 and the exception rules that depend on it.
2. **Tag ruleset for `v*`.** Support is inferred, not proven. As of 2026-09-30 a read-only probe of `gh api repos/rjmurillo/ai-agents/rulesets` returned one ruleset, id 11104075, target `branch`, so rulesets work on this repository. The GitHub REST reference for creating a repository ruleset lists `branch`, `tag`, and `push` as the `target` values and a `creation` rule type. No page read on that date states whether a tag target is available on this plan and visibility, and the API token cannot read the account plan (`plan` returned null). No tag ruleset exists. Live ruleset changes are the owner's to run. The owner command is `gh api -X POST repos/rjmurillo/ai-agents/rulesets` with a body naming target `tag`, `enforcement` `active`, `conditions.ref_name.include` `["refs/tags/v*"]`, rules `creation`, `update`, and `deletion`, and the repository admin role as the only bypass actor. If GitHub refuses that call, the fallback is a CI tag check, and it holds only if the `v*` tag trigger is removed from `publish.yml` so that publishing runs only from the default-branch `workflow_dispatch` entry. A pushed tag runs the tagged commit's own copy of the workflow (decision 5), so the ancestor and tag-match checks cannot protect that route. Until the owner creates the ruleset or drops the tag trigger, the gate is advisory, as decision 5 says, and this accepted record enforces nothing by itself. Creating the ruleset is an owner action tracked under #5636.
3. **Store for the previous manifest.** A GitHub Release holds it as a release asset. The release step runs in a narrowly scoped job with `contents: write`. The rest of `publish.yml` keeps `contents: read`. The job belongs to the default-branch entry workflow. It never checks out candidate code and never deserializes an artifact (ADR-101). It runs only after a promoted publish, so a failed run never becomes the baseline. It uploads to an existing tag and release and does not create either, because `contents: write` could otherwise create a tag and sidestep the tag ruleset.

## Prior Art Investigation

### What Currently Exists

- **Typed results**: `scripts/validation/evidence.py` (issue #5635). Five states, a `revision` field, `aggregate`, `PolicyException`.
- **Governed allowlist shape**: `build/drift_allowlist.py` and `.agents/governance/drift-allowlist.json` (decision D8). Path and reason per entry, a strict loader that raises on a bad file, CODEOWNERS protection.
- **Enforcement planes**: ADR-101. Sets the rule that a verdict comes from a plane above the artifact.
- **Release path**: `.github/workflows/publish.yml`, tag-triggered npm publish with provenance.

### Historical Rationale

The typed states exist because a boolean result let "could not run" read as "clean". The drift allowlist exists because a commit-message marker let one author skip a check on their own word. Both changes moved a decision from prose to a validated record. This ADR applies the same move to release promotion.

### Why Change Now

The epic's acceptance criteria name the missing controls, and the typed results they need are now emitted. Building on `evidence.py` costs less than a second vocabulary.

## Rationale

The design reuses the typed contract instead of adding one. Binding by SHA and digest is the cheapest test that a result describes the thing being promoted. Requiring an approver other than the owner keeps an exception from being self-granted. Failing closed on expiry keeps an old exception from becoming a permanent bypass.

### Alternatives Considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| A. Extend `evidence.py` and add one aggregator (chosen) | Reuses five states, `revision`, and `aggregate`. No second vocabulary. Testable as one program. | Adds fields to the exception type. Needs an applicability table someone maintains. | Chosen |
| B. Rely on GitHub required checks alone | No new code. Already enforced by the ruleset. | Cannot bind to a tarball digest. Cannot express exceptions with owner and expiry. A skipped job can still read as success. | Rejected |
| C. Signed attestations (for example in-toto with Sigstore) | Strong, independently verifiable binding. Industry pattern. | Heavy for one npm package. Needs key or identity policy work first. Does not by itself give exception governance. | Deferred; A leaves room to add it |
| D. Exceptions as PR comments or labels | Fast to write. | Not machine-checkable. No expiry. The gated author can add one. | Rejected |

### Trade-offs

Option A accepts a maintenance cost for the applicability table. The cost is lower than the failure it prevents: a missing check that nobody notices.

## Consequences

### Positive

- A promotion cannot pass on results for a different commit or a different build.
- Every exception has an owner, an approver, and a date it stops working.
- The report says which findings are fixed, accepted, lapsed, and open.

### Negative

- The applicability table is new upkeep. A wrong row either blocks a release or omits a check.
- The approval rule needs a second CODEOWNER identity. The repository has one today, so until then the gate accepts no exceptions (decision 7).
- A malformed exceptions file blocks every promotion, not only the affected finding.
- Digest binding covers the build the workflow produced. It does not prove the source tree was reviewed.

### Neutral

- `publish.yml` changes shape: the publish step moves behind a default-branch entry workflow. That edit is a workflow change with its own security review.

## Impact on Dependent Components

| Component | Impact |
|---|---|
| `scripts/validation/evidence.py` | `CheckOutcome` gains an artifact digest field and a structured `items` field. Exception type gains owner, approval, expiry, remediation fields, or a sibling type does. `aggregate` or the new aggregator compares revisions. |
| Validator jobs | Each uploads its typed result as a JSON evidence artifact. |
| `.github/workflows/publish.yml` and a new default-branch entry workflow | Publish moves behind a default-branch workflow that runs the aggregator, builds once, and re-verifies the digest. |
| Repository rulesets | A tag ruleset restricts `v*` creation. |
| `.github/CODEOWNERS` | Covers the exceptions file and the applicability table. |
| Epic #5636 | The promotion-gate block references this record. |

## Implementation Notes

Nothing is implemented. Sequence now that the record is accepted: the evidence artifact upload from each validator job comes first, because until every applicable validator uploads one, decision 9 makes every green-without-artifact check an `unresolved` finding. Then the exception record schema and loader, then the aggregator with candidate binding, then the `publish.yml` call. Each step is its own change.

## Related Decisions

- ADR-101: Enforcement planes.
- Decision D8 under #5636: the drift allowlist.
- Decision D17 under #5636: the toggle and `continue-on-error` allowlist, merged in #6085. It uses the same owner and expiry fields. This record does not depend on it.
- Decision D21 under #5636: owner acceptance of this record with the answers under Resolved Questions.

## References

- Epic #5636, promotion gate and exception requirements.
- `scripts/validation/evidence.py`
- `.project-toolkit/architecture/ADR-101-enforcement-planes.md`
- `.github/workflows/publish.yml`
