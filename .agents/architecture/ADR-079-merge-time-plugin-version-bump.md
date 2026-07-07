---
id: ADR-079
status: proposed
date: 2026-07-05
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: false
---

# ADR-079: Merge-Time Plugin Version Bump

## Status

Proposed. Requested by issue #2855 (labels `bug`, `agent-qa`, `area-workflows`, `area-infrastructure`, `area-skills`, `priority:P1`, `technical-debt`). The issue surfaces a structural throughput collapse: parallel plugin-source PRs deadlock on the monotonic version-bump gate. The maintainer's grounded evaluation (issue #2855, 2026-07-05) named the precondition directly: the three candidate fixes "all change the release/cache-keying contract that `plugin.json` version participates in. That is an owner design call and warrants an ADR." This ADR is that precondition. It records the release-process contract and recommends a direction. It ships no code.

Recommend invoking the `adr-review` skill (6-agent debate) before acceptance.

## Date

2026-07-05

## Context

Three plugins are published from source directories, each carrying a `.claude-plugin/plugin.json` with a semantic `version`:

- `.claude/.claude-plugin/plugin.json`
- `src/copilot-cli/.claude-plugin/plugin.json`
- `src/claude/.claude-plugin/plugin.json`

Two CI gates govern these versions:

1. **Version-bump gate** (`build/scripts/validate_plugin_version_bump.py`, enforced by `.github/workflows/validate-plugin-version-bump.yml`). When any content file under a packaged plugin's source directory changes in the diff, that plugin's `version` MUST be strictly greater than the version at the base ref. The validator's own docstring states the reason: "Installed plugin caches key off that version: when the version does not change, existing installs never re-sync, so deletions and edits inside the source dir silently fail to reach consumers." This is the silent-staleness bug the gate exists to prevent (issue #1942).

2. **Manifest-parity gate** (`build/scripts/check_plugin_manifest_parity.py`). The `.claude` and `src/copilot-cli` manifests MUST carry identical versions. They currently sit lockstep at `0.6.3`.

The bump is monotonic and evaluated at PR-CI time against the base ref. With K open PRs that each touch plugin source, at most one can hold version `N+1` at a time. When any sibling merges, `main` advances to `N+1`, and every other open PR now equals base and fails the gate. Each must rebase onto `main` and re-bump. Effective merge throughput for plugin-source changes collapses to one PR at a time, with a forced rebase-and-regenerate step between each merge.

The same PRs usually also fail `Validate Generated Files` (`validate-generated-agents.yml`) and `Agent Drift Detection` (`agent-drift-detection.yml`), because a source edit requires regenerating the copilot mirrors, and the regeneration is likewise pinned to a moving base.

Two mitigations already exist and are insufficient:

- **Tactical conflict auto-resolution** (issue #2543). The merge-resolver auto-resolves a version-only `plugin.json` conflict to one patch above the higher side. This reduces conflict thrash but only after a git conflict already exists during rebase. It does not remove the gate serialization.
- **Auto-loaded recovery recipe** (issue #2873, `.github/instructions/plugin-version-bump.instructions.md`). An `applyTo`-scoped instruction file teaches the next agent the `max(open-PR versions)+1` plus immediate-auto-merge recovery. This stops repeated ~15-minute rediscovery but still requires manual, serialized, per-PR bumping.

Three forces drive a decision now:

1. **The collision is structural, not incidental.** As long as the version is hand-set inside the PR and checked against a moving base, K parallel plugin-source PRs cannot all pass the gate. Fleet-scale parallelism makes this the common case, not the edge case.

2. **There is no free bounded relaxation.** Relaxing the PR-time check to `>=` reopens the exact silent-staleness bug (#1942) the gate prevents: a content change under an unchanged version never reaches installed caches. The re-sync guarantee genuinely requires a distinct version per content-changing merge. That is a **merge-time invariant**. The current gate approximates it with a **PR-time** check that cannot know what `main` will be at merge time. The mismatch between where the invariant must hold (merge) and where it is checked (PR) is the root cause.

   The freshness key is `plugin.json` `version` because that is the field the **external** plugin host (the Claude Code / marketplace install-and-cache layer) keys its cache on. This repo publishes the manifest but does not own the consumer's cache-keying protocol. So switching to a content-addressable key (hash of the packaged source) is not a change this repo can make unilaterally; it would require the consumer to accept a non-SemVer freshness key. That option is recorded and rejected in Alternatives (option 4) on that basis.

3. **The tactical fixes have run their course.** #2543 and #2873 address symptoms. The remaining fix changes where and when the version is set, which binds every future plugin-source PR and every release consumer. That is an architecture decision.

## Decision

Move the plugin version bump from PR-authoring time to merge time.

1. **PRs stop hand-editing `version`.** Contributors and fleet agents no longer bump `plugin.json` `version` in a plugin-source PR.

2. **The PR-time version-bump gate relaxes to advisory.** `validate-plugin-version-bump.yml` no longer requires a strictly-greater version. Operationally, "advisory" means: the check still runs and still emits a status, but the status is **non-required** (it cannot block merge), and it warns only on a *downward* version edit (a lowered version is always a mistake). Fleet agents read the non-required status as informational. The strict monotonic guarantee is enforced at merge instead.

3. **A post-merge workflow computes the bump.** A `push`-to-`main` workflow, scoped to commits that touched a packaged plugin's source directory, bumps the affected manifests, regenerates the copilot mirrors, keeps `.claude` and `src/copilot-cli` in parity, and commits the result back to `main` as a dedicated bot commit. Three properties bind the workflow:

   - **Deterministic, idempotent bump rule.** The workflow reads `main` HEAD fresh and sets each affected manifest to `max(current_main_version, any_version_present_in_the_merged_commit) + patch`. Re-running it on an already-bumped commit produces no new commit (idempotent), so a redundant trigger is a no-op rather than a double bump.
   - **Serialized execution.** The workflow declares `concurrency: { group: plugin-version-bump, cancel-in-progress: false }` (queue, do not cancel), per ADR-026. Two plugin-source merges landing seconds apart run one-after-another; the second reads the first's committed version as its base, so no two runs race to the same `N+1`.
   - **Scoped, least-privilege actor.** The bot commits with a GitHub App installation token whose permissions are the minimum needed (contents: write on this repo), not a repo-scoped classic PAT. Before pushing, the workflow asserts `git diff --name-only` against an allow-list (packaged `plugin.json` manifests and generated mirror paths only) and aborts if any out-of-list path is staged. The recursion guard is an **author filter**: the workflow skips when the triggering commit's author is the bot identity. It MUST NOT use `[skip ci]`, which would suppress unrelated required checks (CodeQL, markdown lint) on the bot commit.

4. **The merge-time invariant is preserved by construction.** Every merge that changes plugin content produces exactly one bump. Distinct version per content-changing merge is guaranteed, so the silent-staleness guarantee (#1942) still holds. Cross-PR collision is eliminated because no PR carries a version.

This ADR records the contract and the recommended direction. Implementation ships under a follow-up PR after `adr-review` consensus and owner acceptance. The branch-protection carve-out that lets the bot commit to protected `main` is a repository-admin action and is out of scope for the implementing PR.

## Prior Art Investigation (Required when changing existing systems)

### What Currently Exists

- **Structure/pattern being changed**: the PR-time monotonic version-bump gate (`validate_plugin_version_bump.py`) plus the manifest-parity gate (`check_plugin_manifest_parity.py`), backed by `validate-plugin-version-bump.yml`.
- **When introduced**: the version gate traces to the silent-staleness fix (issue #1942); the tactical conflict resolver to issue #2543; the recovery-recipe instruction file to issue #2873.
- **Original author and context**: repo-owner-driven release-engineering guards to keep installed plugin caches fresh.

### Historical Rationale

- **Why was it built this way?** Installed plugin caches key off `version`. A content change under an unchanged version never re-syncs to consumers (#1942). A strictly-greater bump on every content change prevents that.
- **What alternatives were considered?** #2543 explicitly deferred the structural fix: "stop bumping in PRs and auto-bump on main ... needs an ADR-level decision."
- **What constraints drove the design?** PR-time CI is the cheapest enforcement point and requires no self-committing workflow or branch-protection exception.

### Why Change Now

- **Has the original problem changed?** The freshness requirement is unchanged. What changed is scale: fleet-scale parallel plugin-source PRs are now routine, so the PR-time approximation deadlocks constantly.
- **Is there a better solution now?** Yes. Enforcing the invariant at merge time (where it actually must hold) removes the collision without weakening freshness.
- **What are the risks of change?** A self-committing-to-`main` workflow is a new trusted actor and needs a branch-protection carve-out. A broken generator or bump step would block `main`. Recursion must be prevented (the bump commit must not re-trigger the bump workflow).

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| **1. Post-merge auto-bump workflow (recommended)** | Zero cross-PR collision; distinct version per merge by construction; regeneration moves to merge time, so `Validate Generated Files` and `Agent Drift` churn also disappears; least infra; no merge-queue dependency | Self-committing workflow to protected `main`; needs a branch-protection carve-out for the bot; recursion guard required; a broken bump/generate step blocks `main` | Chosen. Directly targets the root cause (invariant enforced where it must hold) with the least new infrastructure. |
| **2. GitHub merge queue with a bump step** | Keeps `main` always-green; serializes plugin-source merges; queue re-bumps and regenerates the trailing entry before landing; no self-committing-to-`main` workflow | Heavier infrastructure; merge-queue configuration and dependency; still serializes plugin-source merges (throughput bounded by queue) | Not chosen as primary. Higher operational cost; keeps serialization. Recorded as the fallback if the self-commit model is rejected. |
| **3. Pre-PR fleet re-bump + rebase rule (status quo mitigation)** | No new infra; already partially in place via #2873 and #2543 | Still manual and serialized; throughput still collapses to one PR at a time; forces rebase-and-regenerate between every merge | Not chosen. This is the current painful state the issue asks to fix, not a fix. |
| **4. Content-addressable freshness key (hash instead of `version`)** | Eliminates the problem class entirely: no monotonic counter, so parallel PRs never contend; no self-committing bot; staleness impossible by construction | Requires the **consumer** (Claude Code / marketplace install-and-cache layer) to accept a non-SemVer freshness key; this repo publishes the manifest but does not own the consumer's cache-keying protocol, so the change is not unilaterally available | Not chosen. Out of this repo's control. The freshness key is SemVer `version` because the external host keys its cache on that field (see Context, force 2). Recorded because it is the correct fix *if* the consumer protocol were ours to change; it is not. |
| **0. Do nothing** | No work | The P1 throughput collapse persists; blocks batches of useful fix PRs (issues #2841, #2842, #2845, #2847 were cited as blocked) | Not chosen. The issue is a live P1 with confirmed recurrence. |

### Trade-offs

Option 1 trades a small, bounded increase in release-pipeline trust surface (one bot that commits version bumps to `main`) for the removal of an unbounded, fleet-scaling coordination cost. The trust surface is auditable and enforced: the bot commit only edits `plugin.json` versions and generated mirrors, constrained to those paths by a pre-push allow-list assertion in the workflow (Decision item 3), not by convention alone, and the bot uses a least-privilege GitHub App token rather than a repo-scoped PAT. The coordination cost, by contrast, grows with fleet size and has no bounded relaxation (force 2 in Context).

## Consequences

### Positive

- Parallel plugin-source PRs never collide on version. Merge throughput no longer collapses to one-at-a-time.
- The silent-staleness guarantee (#1942) is preserved: exactly one bump per content-changing merge.
- Regeneration of copilot mirrors moves to merge time, so the coupled `Validate Generated Files` and `Agent Drift Detection` failures on parallel PRs also disappear.
- The recovery-recipe instruction file (#2873) and the tactical conflict resolver (#2543) become unnecessary for version conflicts.

### Negative

- A workflow that commits to protected `main` is a new trusted actor and requires a branch-protection carve-out (repo-admin action, out of scope for the implementing PR).
- A broken bump or regenerate step blocks `main` until fixed, converting a per-PR failure into a trunk failure. See Failure Recovery below.
- Recursion risk: the bump commit must not re-trigger the bump workflow. Bound to an author filter on the bot identity (not `[skip ci]`, which would suppress unrelated required checks).
- A transient merge-to-bump window exists: between a content-changing merge landing on `main` and the bot's bump commit, `main` HEAD carries changed content under an unchanged version. This is safe for the stated use case because installed caches key off **released** versions, not `main` HEAD. Any future consumer that installs directly from `main` HEAD would observe stale-cache behavior in that window (seconds to a few minutes, bounded by the serialized workflow runtime).
- Local installs and any consumer that inspects the PR-branch version will no longer see a bumped version until after merge.

### Failure Recovery

The post-merge model moves the failure surface from per-PR (fail-closed, recoverable by the PR author) to trunk (fail-open on the freshness invariant if the bump silently fails). Three controls bound this:

- **Reconciliation detector.** A scheduled workflow re-checks `main` for any content-changing commit whose plugin manifest was not bumped, and opens an issue (or alerts) if it finds one. This restores the detective signal that the advisory PR gate gives up.
- **Rollback trigger.** If the post-merge bump workflow fails N consecutive times (default N=2), the reconciliation detector re-enables the PR-time gate as blocking (via a repository variable the two workflows share), reverting to the known-good fail-closed behavior until the bump workflow is fixed.
- **Idempotent re-run.** Because the bump rule is `max(...) + patch` and idempotent (Decision item 3), a maintainer can safely re-run the workflow on the failed commit without producing a double bump.

### Neutral

- The manifest-parity gate (`check_plugin_manifest_parity.py`) stays; the post-merge workflow keeps `.claude` and `src/copilot-cli` in parity when it bumps.
- The version scheme (SemVer 2.0.0 core, strictly-greater precedence) is unchanged; only the actor and timing of the bump change.

## Impact on Dependent Components

| Component | Dependency Type | Required Update | Risk |
|-----------|----------------|-----------------|------|
| `.github/workflows/validate-plugin-version-bump.yml` | Direct | Relax from blocking to advisory (warn on content change, do not require a bump) | Medium |
| `build/scripts/validate_plugin_version_bump.py` | Direct | Add an advisory mode or gate its blocking behavior behind the new post-merge model | Medium |
| New post-merge bump workflow | New | Add a `push`-to-`main`, plugin-path-scoped workflow that bumps affected manifests, regenerates mirrors, keeps parity, and commits back with a recursion guard | High |
| `.github/workflows/validate-generated-agents.yml`, `.github/workflows/agent-drift-detection.yml` | Indirect | Mirror regeneration moves to merge time; PR-time drift checks become advisory for plugin-source PRs | Medium |
| `.github/instructions/plugin-version-bump.instructions.md` (#2873) | Indirect | Retire or rewrite once PRs no longer hand-bump | Low |
| Tactical merge-resolver auto-bump (#2543) | Indirect | Version-conflict path becomes dead code once PRs carry no version | Low |
| Repository branch protection | Direct | Admin carve-out so the bump bot can commit to protected `main` | High |
| Bump bot credential (GitHub App) | New | Provision a GitHub App installation token scoped to `contents: write`; no repo-scoped classic PAT | High |

## Implementation Notes

Suggested sequence for the follow-up implementing PR (not part of this ADR):

1. Add the post-merge bump workflow behind a feature branch. Path-filter to packaged plugin source dirs. Declare `concurrency: { group: plugin-version-bump, cancel-in-progress: false }` (ADR-026). Add the author-filter recursion guard (skip when the triggering commit author is the bot identity).
2. Add tests for the bump/regenerate module (ADR-006 principle: logic in a tested module, workflow orchestrates only; language is Python per ADR-042). Tests MUST cover the idempotent `max(...) + patch` rule and the pre-push path allow-list assertion.
3. Relax the PR-time gate to advisory in the same PR so the two do not fight (non-required status; warn on downward version edits).
4. Add the reconciliation detector and the N-consecutive-failure rollback trigger (Failure Recovery).
5. Separately (owner-admin), provision a GitHub App installation token (`contents: write`), grant the bump bot write to protected `main`, and rely on the workflow's pre-push allow-list assertion to constrain the commit to `plugin.json` and generated mirror paths. Note: GitHub branch protection cannot path-scope a bypass actor's write; the path constraint is enforced in the workflow, not by branch protection. Prefer a repository ruleset with a path-restricted bypass if that feature is available at implementation time.

## Acceptance Criteria

The implementing PR is done when:

1. K parallel plugin-source PRs (K >= 2) merge in any order with no manual version edit and no cross-PR version collision.
2. No commit on `main` carries a plugin-source content change without a corresponding version bump landing within 15 minutes, verified by one scheduled reconciliation-detector run confirming zero unbumped content commits.
3. The bump workflow is idempotent: re-running it on an already-bumped commit produces no new commit.
4. Two plugin-source merges landing within the workflow runtime produce two distinct, monotonically increasing versions (no race, no duplicate).
5. The bot commit changes only allow-listed paths; a workflow bug that stages any other path aborts before push.
6. `.claude` and `src/copilot-cli` remain at identical versions after every bump (manifest-parity gate stays green).

## Related Decisions

- ADR-006 (thin workflows, testable modules): the new bump logic MUST live in a tested module, not inline YAML. Per ADR-042 (Python migration strategy), that module is Python.
- ADR-026 (PR automation concurrency and safety controls): the post-merge workflow MUST adopt its concurrency-group pattern so rapid successive merges serialize rather than race.
- ADR-072 (JTBD plugin architecture): defines the packaged-plugin model whose versions this ADR governs.
- Issue #2543 (tactical merge-resolver auto-bump), issue #2873 (auto-loaded recovery recipe), issue #1942 (silent-staleness bug the version gate prevents).

## References

- Issue #2855 (this ADR's request and evidence).
- `build/scripts/validate_plugin_version_bump.py` (RULE docstring).
- `build/scripts/check_plugin_manifest_parity.py` (manifest parity).
- `.github/workflows/validate-plugin-version-bump.yml`, `.github/workflows/validate-generated-agents.yml`, `.github/workflows/agent-drift-detection.yml`.
- `.github/instructions/plugin-version-bump.instructions.md`.
- SemVer 2.0.0 (https://semver.org/#spec-item-11).
