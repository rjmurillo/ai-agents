---
id: ADR-096
status: accepted
date: 2026-08-16
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: false
---

# ADR-096: Trusted vendor provenance gate

## Status

Accepted after four ADR review rounds. The final vote was 6 of 6 ACCEPT.
See `.agents/critique/ADR-096-debate-log.md`.

## Date

2026-08-16

## Context

This repository ships hooks, generated plugin files, and vendored dependencies.
A pull request can alter the workflow or validator that reviews those same
files. A normal `pull_request` workflow evaluates candidate-owned workflow code.
That cannot protect its own trust boundary.

The gate must satisfy these constraints:

1. Execute workflow and validator code from the base commit.
2. Never import or execute candidate Python, JavaScript, or hooks.
3. Validate the candidate by immutable commit SHA and Git tree objects.
4. Publish a required result on the pull request head SHA.
5. Prevent a prior success on an unchanged SHA from masking revalidation.
6. Authenticate every repository-owned executable and configuration file used
   before verdict.
7. Fail closed on missing files, API failures, malformed inputs, and drift.

## Decision

Use a base-owned `pull_request_target` workflow with a standalone Python
validator.

The workflow and validator follow these rules:

1. The workflow fetches immutable event SHAs. It never fetches branch names.
2. The workflow materializes trusted base and candidate trees with
   `git read-tree` and `git checkout-index`.
3. The candidate tree is data only. No candidate file is executed or imported.
4. A pending Commit Status is published on the pull request head before Git
   materialization. This marker is best-effort because the trusted validator
   is not yet available.
5. After trusted base materialization, `_start_head_gates` retries and attempts
   both head channels: pending Commit Status and in-progress Check Run.
6. `_finish_head_gates` attempts both final channels and aggregates failures.
   The Check Run is patched by ID. No fallback row is created.
7. Workflow runs use a per-pull-request concurrency group with cancellation.
8. The validator pins every repository-owned executable, generator, manifest,
   and configuration file in its execution closure with SHA-256.
9. Pin changes require trusted author and sender numeric GitHub user IDs.
   Mutable login names are not authorization identities. Unknown IDs cannot
   modify or delete the gate.
10. The workflow does not subscribe to `merge_group`. That event executes from
    the synthetic queue head, so candidate changes can replace a privileged
    workflow that relies on `pull_request_target` base ownership. Merge queue
    support requires a separate base-owned execution design before activation.
    This user-owned repository is currently ineligible for merge queues; the
    boundary still applies if repository ownership or platform support changes.
11. The workflow rejects gitlinks, escaping symlinks within the trusted scan
    roots, unpinned executables,
    `.npmrc`, `uv.toml`, unsafe markdownlint configuration, and mirror drift.
    Gitlink rejection is repository-wide and runs before relevance filtering.
    This repository does not permit submodules because a gitlink delegates code
    identity to an external repository outside this gate's authenticated tree.
12. Lockfile reconstruction installs candidate-declared npm packages with
    `npm ci --ignore-scripts` only after registry, scheme, and SHA-512 integrity
    validation. It does not execute package lifecycle scripts.
13. All pipeline and validation failures return non-zero. No success-shaped
    fallback satisfies the required result.

The hosted GitHub runner and its preinstalled `timeout`, `gh`, `rm`, `git`,
and `python3` commands are platform trust roots. Setup actions are pinned to
immutable commits. Python, uv, and Node.js versions are exact. SHA-256 pins
cover the repository-owned execution closure, not the hosted toolchain.

The workflow exceeds ADR-006's 100-line target. The excess is orchestration:
immutable Git materialization, dual head-state publication, and tool setup.
Policy and parsing remain in tested Python.

### ADR-006 exception request

**Scope**: `.github/workflows/vendor-provenance.yml` only.

#### Chesterton's Fence analysis

ADR-006 states:

> GitHub Actions workflows cannot be tested locally. The feedback loop is:
> 1. Edit workflow YAML 2. Commit and push 3. Wait for CI to run (1-5 minutes)
> 4. Check results 5. If failed, repeat from step 1. This **slow OODA loop**
> makes workflow debugging painful and time-consuming.

The rule prevents policy logic from becoming untestable YAML. ADR-096 keeps
authorization, pin validation, tree inspection, and GitHub API orchestration
in `scripts/ci/validate_vendor_provenance.py`, with pytest coverage. The
workflow has 181 total lines and 125 non-comment lines. The 25 non-comment
lines above ADR-006's target express GitHub-owned trust boundaries:
permissions, trusted event selection, concurrency, immutable base and candidate
fetches, worktree materialization, and exact runtime inputs. Moving those
boundaries out of the workflow would hide the security contract rather than
make it more testable.

#### Alternatives attempted

| Alternative | Outcome | Evidence |
|-------------|---------|----------|
| Move status and Check Run orchestration into the Python validator | Adopted in part. `_start_head_gates` and `_finish_head_gates` removed API policy from YAML. Immutable checkout and trusted bootstrap must remain visible before candidate Python can exist. | `scripts/ci/validate_vendor_provenance.py`, `TestHeadGateOrchestration` |
| Replace workflow wiring with a local composite action | Rejected. A repository action is unavailable before trusted base materialization. A third-party action would enlarge the privileged supply-chain closure. | The workflow materializes the trusted base before invoking repository-owned executables. |

#### Impact and boundary

- **Debt created**: 181 total workflow lines, with 125 non-comment lines,
  instead of ADR-006's 100-line target.
- **Testing impact**: workflow syntax and wiring use `actionlint`,
  `validate_github_workflows.py`, and static workflow tests. Policy logic stays
  in pytest-covered Python.
- **Precedent risk**: narrow. This exception permits no other workflow, no
  business logic in YAML, and no candidate-owned executable before trusted
  materialization.
- **Reversibility**: delete this workflow and remove both required contexts.
  If GitHub exposes a smaller trusted primitive, migrate the wiring and retire
  this exception.
- **Review trigger**: any increase above 125 non-comment lines requires a new
  ADR review and evidence that policy logic did not move into YAML.

### Bootstrap ordering

Land the workflow and validator before configuring the status as required.
Observe at least one `edited` or `reopened` event on an existing pull request.
Then require the `Validate Vendor Provenance` context.

Do not enable merge queue support before the direct pull request context is
required and verified. Merge queue enablement requires a separate base-owned
execution design and security review.

Trusted pin updates MAY land the artifact and matching content hash together.
The validator parses the candidate pin table as data and accepts it only when
the pull request author and event sender are trusted. A follow-up pin commit is
preferred when it makes review and QA binding clearer, but it is not required
by the validator.

### Failure policy

Transient GitHub API failures receive three bounded attempts. Authentication
and validation errors fail immediately.

If Check Run completion fails, the in-progress Check Run remains blocking. If
Commit Status completion fails, the Check Run still records the verdict. If
both GitHub APIs are unavailable, repository code cannot publish a new head
state. The workflow fails visibly. This platform outage is an accepted
residual risk.

If trusted base materialization fails before an in-progress Check Run exists,
the pre-materialization Commit Status is the blocking head signal. A prior
Check Run can remain visible beside it. This design depends on branch rules
requiring both same-named contexts to pass. Verify that platform behavior in a
repository smoke test before enabling the required context.

### Rollback

Do not bypass the gate. If the gate causes a repository-wide outage:

1. Remove the required context through repository administration.
2. Revert the gate change through normal review.
3. Repair pins or runtime behavior.
4. Re-enable the required context after an `edited` or `reopened` smoke run.

Branch-ruleset administration is the break-glass control. ADR-066 D8's
environment valve applies to local hooks that can wedge a live loop. A
required hosted status check has no local process valve. Prefer reverting one
bad pin commit over reverting the entire gate.

The repository owner or an administrator performs rollback. Target
time-to-mitigate is 30 minutes after receiving a GitHub Actions failure
notification for confirmed repository-wide blockage. Confirm blockage when
two unrelated pull requests at the same base SHA fail the required context
with the same workflow-side error, or when the failure reproduces against an
unchanged `origin/main`. Re-run every open pull request after restoring the
required context.

## Prior Art Investigation

### What Currently Exists

- ADR-006 keeps workflow YAML thin and moves policy into testable Python.
- ADR-026 defines per-PR workflow concurrency and cancellation.
- ADR-066 requires invariant gates to fail closed and loud.
- ADR-093 requires equivalent evidence before declaring a remote check fixed.
- PR #4846 implements the vendor provenance workflow and validator.

### Historical Rationale

The repository already pins GitHub Actions to immutable SHAs. That protects
action source, but not repository-owned scripts and generated artifacts loaded
before a security verdict. The provenance gate extends immutable identity to
that local execution closure.

### Why Change Now

Architect Review run 31923412646 on PR #4846 identified the privileged trigger,
candidate isolation, pin governance, bootstrap sequence, rollback, and failure
policy as an undocumented architecture contract. The code exists. The decision
record must land before the gate becomes required.

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Normal `pull_request` workflow | Native checks attach to the pull request | Candidate controls workflow and validator changes | Cannot protect its own trust boundary |
| `pull_request_target` plus `actions/checkout` | Simple repository checkout | Checkout behavior and candidate directives enlarge the trusted surface | Git tree materialization is smaller and explicit |
| Checks API only | Rich check output | An API failure can leave a prior status visible | Dual head channels reduce one-service failure risk |
| Commit Status API only | Simple pending and final states | Less structured output and weaker run identity | Check Run IDs provide one-writer completion |
| CODEOWNERS and required review only | Native control with low maintenance | Reviews intent, not executable byte identity or generated drift | Complements but does not replace provenance |
| External service | Separate trust domain | New credentials, operations, cost, and outage modes | Repository-owned gate is testable and sufficient |

### Trade-offs

The design duplicates verdict state across Checks and Commit Status APIs. This
adds code and tests. It also prevents one API family from being the only path
to a head verdict.

The pin table creates maintenance work whenever trusted files change. That cost
is intentional. An unreviewed executable must not enter the trusted closure.

## Consequences

### Positive

- Candidate code cannot modify the validator that executes for its own review.
- Every trusted repository-owned executable has immutable identity.
- Edited and reopened pull requests receive a fresh pending head state.
- Missing or malformed trust inputs block instead of degrading to success.
- Concurrency limits competing verdict writers on one pull request.

### Negative

- Base changes can invalidate open branches until pins refresh.
- The workflow depends on GitHub APIs for head-state publication.
- Pin maintenance can cause repeated CI cycles in a high-merge repository.
- Any pull request adding a gitlink is blocked, including paths outside the
  vendor provenance relevance set.
- A total GitHub API outage cannot replace an old head status.
- Vendor reconstruction depends on registry access and fails closed on outage.
- `_TRUSTED_UPDATE_ACTOR_IDS` contains one immutable numeric identity. This
  matches the current
  single-maintainer model and has no in-repository succession path. Compromise
  of that account defeats this repository's maintainer-level controls, not only
  this gate. Adding a second trusted actor requires its own reviewed change.

Revisit the pin-table design if one pull request needs more than two pin refresh
cycles, or if pin refreshes exceed five commits in seven days. The replacement
candidate is a separate authenticated manifest with a smaller review surface.

### Neutral

- The workflow uses `pull_request_target`, so permissions require periodic
  security review.
- Non-required external scanners remain separate from this gate.

## Impact on Dependent Components

| Component | Dependency Type | Required Update | Risk |
|-----------|----------------|-----------------|------|
| `.github/workflows/vendor-provenance.yml` | Direct | Keep the pull-request-only trigger, permissions, concurrency, and head-gate ordering aligned | High |
| `scripts/ci/validate_vendor_provenance.py` | Direct | Keep pin closure and dual head-gate state machine aligned | High |
| `tests/ci/test_validate_vendor_provenance.py` | Direct | Cover pins, API failures, ordering, and production tree | Medium |
| Branch ruleset, direct PR merge | External | Require context only after smoke validation | High |
| Merge queue configuration | External | Keep disabled until a base-owned execution design and security review land | High |
| Hook and generator changes | Indirect | Refresh pins in a follow-up evidence commit | Medium |
| `secrets.VENDOR_PROVENANCE_PAT` | External | Fine-grained, single-repo, contents-read token; rotate or use `github.token` fallback | Medium |
| npm registry | External | Supplies integrity-pinned packages for reconstruction; outage blocks | Low |

## Implementation Notes

PR #4846 carries the initial implementation. `implemented` remains false until
the ADR and gate implementation merge.

### Confirmation

- Dual head-gate ordering and aggregation:
  `TestHeadGateOrchestration`, `TestPublishCheckRun`,
  `TestCreateCheckRun`, and `TestPublishCommitStatus`.
- Trust-anchor self-protection and actor authorization:
  `TestTrustAnchorSelfProtection`, `TestTrustAnchorAuth`, and
  `TestTrustedUpdateAuthorization`.
- Gitlink, symlink, mirror, and lockfile checks:
  `TestRejectGitlinks`, `TestPathComponentSymlinks`, `TestMirrorParity`, and
  `TestLockfilePolicy`.
- Immutable-SHA workflow contract: `TestWorkflowImmutableBaseRef`.
- Pin and relevance agreement:
  `test_every_pinned_artifact_triggers_relevance`.
- Candidate configuration and executable rejection:
  `TestUnpinnedExecutables`, `TestNpmrcRejection`, `TestUvTomlRejection`,
  `TestRootMarkdownlintConfigInjection`, and `TestMarkdownlintConfigPolicy`.
- PR #4846 reports author and sender user ID `6811113`, matching
  `_TRUSTED_UPDATE_ACTOR_IDS`. A successful trusted-update workflow run must
  still verify both event IDs before required-check activation.

Review this ADR before merge queue enablement, when a second trusted maintainer
is added, or when the pin-refresh threshold above is exceeded.

## Related Decisions

- [ADR-006](./ADR-006-thin-workflows-testable-modules.md)
- [ADR-026](./ADR-026-pr-automation-concurrency-and-safety.md)
- [ADR-066](./ADR-066-hook-fail-open-reconciliation.md)
- [ADR-093](./ADR-093-verify-red-checks-with-the-same-checker.md)

## References

- GitHub Actions `pull_request_target` event documentation
- GitHub Checks API documentation
- GitHub Commit Status API documentation
- CWE-829, Inclusion of Functionality from Untrusted Control Sphere
- PR #4846
